import csv
import time
from astropy.io import fits as pyfits
import numpy as np
from FileUtils import *
import scipy.ndimage
from PhotonTools import *
from MCUtils import *
from CalUtils import *
from gnomonic import *
import cal

GPSSECS = 315532800+432000

def load_txy(csvfile):
	"""Loads just the t,x,y columns from a photon CSV file."""
	reader = csv.reader(open(csvfile,'rb'),delimiter=',',quotechar='|')
	t,x,y,xa,ya,q,xi,eta,ra,dec,flags=[],[],[],[],[],[],[],[],[],[],[]
	columns = ['t','x','y','xa','ya','q','xi','eta','ra','dec','flags']
	for row in reader:
		t.append(float(row[0])/1000.)
		x.append(float(row[1]))
		y.append(float(row[2]))
		#xa.append(float(row[3]))
		#ya.append(float(row[4]))
		#q.append(float(row[5]))
		#xi.append(float(row[6]))
		#eta.append(float(row[7]))
		#ra.append(float(row[8]))
		#dec.append(float(row[9]))
		flags.append(float(row[10]))

	return np.array(t),np.array(x),np.array(y),np.array(flags,dtype='int16')

def compute_deadtime(t,x,y,band,eclipse,trange=[[],[]]):
	"""Uses multiple methods to estimate the detector deadtime correction.
	The deadtime is an estimate of the fraction of time that the detector was
	unable to register new events because it was in the middle of readout.
	Deadtime should, therefore, not count as true exposure time.
	"""
	print "Computing deadtime correction..."
	refrate = 79.0 # counts per second
	minrate = refrate*.4
	maxrate = refrate+2.
	maxdiff = 0.1
	feeclkratio = 0.966
	tstep = 1. # seconds
	tec2fdead = 5.52e-6 # conversion from TEC to deadtime correction

	if not trange[0]:
		trange[0] = min(t)
	if not trange[1]:
		trange[1] = max(t)

	exptime = trange[1]-trange[0]

	stimt,stimx_as,stimy_as,stimix=find_stims(t,x,y,band,eclipse)
	print "Located "+str(len(stimt))+" stim events."

	dead = 0.
	# Compute using an emperical formula -- Method 1
	dead0 = tec2fdead*(len(t)/exptime)/feeclkratio
	print "	Simple correction w/ Method 1: "+str(dead0)

	# Toss more error checking into here esp. wrt minrate and maxrate
	if exptime<=tstep:
		tstep = 0.01
		bins = np.linspace(0.,exptime-exptime%tstep,exptime//tstep+1)
		dead2 = (1.-((len(stimt)/exptime)/feeclkratio)/refrate)
	else:
		bins = np.linspace(0.,exptime-exptime%tstep,exptime//tstep+1)
		h,xh = np.histogram(stimt-trange[0],bins=bins)
		ix = ((h<=maxrate) & (h>=minrate)).nonzero()[0]
		dead2 = (1.-((h[ix]/tstep)/feeclkratio)/refrate).mean()

	h,xh = np.histogram(t-trange[0],bins=bins)
	dead1 = (tec2fdead*(h/tstep)/feeclkratio).mean()
	print "	Correction w/ Method 1:        "+str(dead1)
	print "	Correction w/ Method 2:        "+str(dead2)

	# For short time slices, the "best" deadtime estimation method
	#  doesn't work very well.
	if exptime<=5.:
		print "Short exposure. Using Method 1."
		dead = dead1
		if (abs(dead1-dead0)>maxdiff):
			print "Warning: Deadtime corrections are suspect."
	else:
		print "Using Method 2."
		dead = dead2
		if (abs(dead2-dead1)>maxdiff):
			print "Warning: Deadtime corrections are suspect."

	return dead

def compute_shutter(t,trange=[[],[]]):
	"""Computes the detector shutter correction.
	The shutter correction accounts for short periods of time when no events
	were registered by the detector for any number of reasons. Any gap of
	longer than 0.05 seconds does not count as true exposure time.
	"""
	if not trange[0]:
		trange[0]=min(t)
	if not trange[1]:
		trange[1]=max(t)
	exptime = trange[1]-trange[0]
	tstep = 0.05 # seconds

	bins = np.linspace(0.,exptime-exptime%tstep,exptime//tstep+1)
	h,xh = np.histogram(t-trange[0],bins=bins)

	# If no counts are recorded for a tstep interval, consider the
	#  virtual shutter to have been effectively closed during that time
	gaps = len((h==0).nonzero()[0])

	return gaps*tstep

def compute_exposure(t,x,y,flags,band,eclipse,trange=[[],[]]):
	"""Computes the effective or true exposure for the given data."""
	# Use only unflagged data.
	# This should be done at the database level.
	ix = ((flags!=7) & (flags!=12)).nonzero()[0]
	if not len(ix):
		print "No unflagged data."
		return 0.
	if not trange[0]:
		trange[0] = min(t[ix])
	if not trange[1]:
		trange[1] = max(t[ix])
	exptime=trange[1]-trange[0]
	print "Gross exposure time is "+str(exptime)+" seconds."
	deadtime = exptime*compute_deadtime(t,x,y,band,eclipse,trange=trange)
	print "Removing "+str(deadtime)+" seconds of exposure from deadtime."
	ix = (flags==0).nonzero()[0]
	shutter = compute_shutter(t[ix],trange=trange)
	if shutter:
		print "Removing "+str(shutter)+" seconds of exposure from shutter."
	print "Corrected exposure is "+str(exptime-deadtime-shutter)+" seconds."

	return exptime-deadtime-shutter

# FIXME: This doesn't get used anywhere.
#def compute_exposure2(csvfile,band,eclipse):
#	"""This function only still exists for reference."""
	# This computation is done a big, terrible, slow loop because
	#  NUV csv files are too big to hold in memory on most machines
	#  so I can't just use the numpy functions.
	# I need the min and max photon times before computing deadtime
	#  so that I can create the correct bins for the histograms below
#	print "Computing exposure from ",csvfile
#	print "		band=",band,"	eclipse=",eclipse
#	print "Finding min/max photon times..."
#	mint,maxt,tot=0.,0.,0.
#	reader = csv.reader(open(csvfile,'rb'),delimiter=',',quotechar='|')
#	for row in reader:
#		tot+=1
#		if (float(row[10])!=7) and (float(row[10])!=12):
#			t = float(row[0])/1000.
#			if mint==0 or t<mint:
#				mint=t
#			if maxt==0 or t>maxt:
#				maxt=t
#
#	print "		Total photos: "+str(tot)
#	print "		Time range:    ["+str(mint)+","+str(maxt)+"]"
#	exptime=maxt-mint
#	print "		Raw exposure: "+str(exptime)
#
#	print "Computing dead time and shutter corrections..."
#	tstep=1. # seconds; time resolution of the dead time correction
#	t,x,y,flags=[],[],[],[]
#	cnt,chunk,n,shutter=0,0,0,0
#	matchtimes=0 # Placeholder for restrictinng the time range
#	chunksz=1000000 # Load values into memory in this size chunk
#	bins = np.linspace(0.,exptime-exptime%tstep,exptime//tstep+1)
#	h1,h2 = np.zeros(len(bins)-1),np.zeros(len(bins)-1)
#	reader = csv.reader(open(csvfile,'rb'),delimiter=',',quotechar='|')
#	for row in reader:
#		n+=1
#		cnt+=1
#		if cnt<chunksz and not (chunk*chunksz+cnt==tot):
#			t.append(float(row[0])/1000.)
#			x.append(float(row[1]))
#			y.append(float(row[2]))
#			flags.append(float(row[10]))
#		elif cnt==chunksz or (chunk*chunksz+cnt)==tot:
#			t,x,y,flags=np.array(t),np.array(x),np.array(y),np.array(flags)
#			chunk+=1
#			print_inline(str(chunk*chunksz)+"/"+str(tot))
#			ix = ((flags!=7) & (flags!=12)).nonzero()[0]
#			stimt,stimx_as,stimy_as,stimix=find_stims(t[ix],x[ix],y[ix],band,eclipse)
#			h,xh = np.histogram(t[ix]-mint,bins=bins)
#			h1+=h
#			h,xh = np.histogram(stimt-mint,bins=bins)
#			h2+=h
#			ix = (flags==0).nonzero()[0]
#			if len(ix)>0:
#				shutter+=compute_shutter(t[ix])
#			t,x,y,flags=[],[],[],[]
#			cnt=0
#
#	print_inline("		Processed "+str(n)+" total events.")
#
#	print "		Shutter correction is "+str(shutter)+" seconds."
#
#	refrate = 79.0 # counts per second
#	minrate = refrate*.4
#	maxrate = refrate+2.
#	maxdiff = 0.1
#	feeclkratio = 0.966
#	tstep = 1. # seconds
#	tec2fdead = 5.52e-6 # conversion from TEC to deadtime correction
#
#	# Compute using an empirical formula -- Method 1
#	dead0 = tec2fdead*(tot/exptime)/feeclkratio
#	print "		Simple dead time correction w/ Method 1: "+str(dead0)
#
#	# Compute using an advanced version of the empirical formula -- Method 1+
#	# This doesn't work correctly right now for some reason
#	dead1 = (tec2fdead*(h1/tstep)/feeclkratio).mean()
#	print "		Dead time correction w/ Method 1: "+str(dead1)
#
#	# Perform the computation "correctly." -- Method 2
#	#  This should more or less match Method 1 above.
#	ix = ((h2<=maxrate) & (h2>=minrate)).nonzero()[0]
#	dead2 = (1.-((h2[ix]/tstep)/feeclkratio)/refrate).mean()
#	print "		Dead time correction w/ Method 2: "+str(dead2)
#
#	if abs(dead2-dead0)>maxdiff:
#		print "Warning: The deadtime correction is suspect."
#
#	exptcorr = exptime-(exptime*dead2)-shutter
#	print "Corrected exposure time: "+str(exptcorr)+" seconds ("+str(exptcorr/60.)+" min.)"
#
#	return exptcorr

def create_rr(csvfile,band,eclipse,aspfile=0.,expstart=0.,expend=0.,retries=20):
	"""Creates a relative response map for an eclipse, given a photon list."""
	detsize = 1.25
	pltscl = 68.754932
	aspum = pltscl/1000.0

	print "Loading flat file..."
	flat, flatinfo = cal.flat(band)
	npixx = flat.shape[0]
	npixy = flat.shape[1]
	pixsz = flatinfo['CDELT2']
	flatfill = detsize/(npixx*pixsz)

	print "Retrieving aspect data..."
	if aspfile:
		aspra, aspdec, asptwist, asptime, aspheader, aspflags = load_aspect([aspfile])
	else:
		aspra, aspdec, asptwist, asptime, aspheader, aspflags = web_query_aspect(eclipse,retries=retries)
	minasp = min(asptime)
	maxasp = max(asptime)
	print "			trange= ( "+str(minasp)+" , "+str(maxasp)+" )"
	ra0, dec0, roll0 = aspheader['RA'], aspheader['DEC'], aspheader['ROLL']
	print "			[RA, DEC, ROLL] = ["+str(ra0)+", "+str(dec0)+", "+str(roll0)+"]"

	print "Computing aspect vectors..."
	print "Calculating aspect solution vectors..."
	xi_vec, eta_vec = np.array([]), np.array([])
	#for i, ra in enumerate(aspra):
		#xi, eta = gnomfwd_simple(ras[i],decs[i],ra0,dec0,-twists[i], 1.0/36000.0, 0.)
		#xi, eta = gnomfwd_simple(ra0,dec0,ras[i],decs[i],-twists[i], 1.0/36000.0, 0.)
	xi_vec, eta_vec = gnomfwd_simple(ra0,dec0,aspra,aspdec,-asptwist, 1.0/36000.0, 0.)
		#xi_vec = np.append(xi_vec,xi)
		#eta_vec = np.append(eta_vec,eta)

	flat_scale = compute_flat_scale(asptime.mean(),band)

	#startt=time.time()
	if not expstart:
		expstart = asptime.min()+GPSSECS
	if not expend:
		expend = asptime.max()+GPSSECS
	flatbuff = np.zeros([960,960])
	# Rotate the flat into the correct orientation to start
	flatbuff[80:960-80,80:960-80] = np.flipud(np.rot90(flat))
	expt = 0
	rr = np.zeros([960,960])
	col = ((( xi_vec/36000.)/(detsize/2.)*flatfill + 1.)/2. * npixx)-400.
	row = (((eta_vec/36000.)/(detsize/2.)*flatfill + 1.)/2. * npixy)-400.
	#print len(asptime),len(xi_vec),len(eta_vec),len(col),len(row)
	for i in xrange(len(asptime)-1):
		#print i
		if (asptime[i]+GPSSECS)<expstart or (asptime[i]+GPSSECS)>expend:
			print "		",asptime[i]+GPSSECS," out of range."
			continue
		elif (aspflags[i]%2!=0) or (aspflags[i+1]%2!=0):
			continue
			print "		",asptime[i]+GPSSECS," flagged."
		else:
			#print "ping"
			rr += scipy.ndimage.interpolation.shift(scipy.ndimage.interpolation.rotate(flatbuff,-asptwist[i],reshape=False,order=0,prefilter=False),[col[i],row[i]],order=0,prefilter=False)
			#print time.time()-startt
			#startt=time.time()
			expt+=1

	# Need to modify this to handle NUV files better.
	t,x,y,flags=load_txy(csvfile)
	exp = compute_exposure(t,x,y,flags,band,eclipse)
	deadt = compute_deadtime(t,x,y,band,eclipse)

	return rr*flat_scale*(1-deadt),exp

def write_rr(csvfile,band,eclipse,rrfile,outfile,aspfile=0,expstart=0.,expend=0.,exptime=0.,imsz=960.,retries=20):
	"""Creates a relative response map for an eclipse, given a photon list file,
	and writes it to a FITS file.
	"""
	rr,exptime = create_rr(csvfile,band,eclipse,aspfile,expstart,expend,retries=retries)

	#aspra, aspdec, asptwist, asptime, aspheader, aspflags = load_aspect([aspfile])
        if aspfile:
                aspra, aspdec, asptwist, asptime, aspheader, aspflags = load_aspect([aspfile])
        else:
                aspra, aspdec, asptwist, asptime, aspheader, aspflags = web_query_aspect(eclipse,retries=retries)

	ra0, dec0, roll0 = aspheader['RA'], aspheader['DEC'], aspheader['ROLL']

	if not expstart:
		mint = asptime.min()
	else:
		mint=expstart

	if not expend:
		maxt = asptime.max()
	else:
		maxt=expend

	hdulist = pyfits.open(rrfile)
	hdr = hdulist[0].header
	hdulist.close()
	hdr.update(key='expstart',value=mint)
	hdr.update(key='expend',value=maxt)
	if exptime:
		hdr.update(key='exptime',value=exptime)
	pyfits.writeto(outfile,rr,hdr,clobber=True)

	return

def write_rrhr(rrfile,rrhrfile,outfile):
	"""Turns a relative response (rr) into a high resolution relative response (rrhr) file with interpolation."""
	hdulist1 = pyfits.open(rrfile)
	hdr1 = hdulist1[0].header
	hdulist1.close

	hdulist0 = pyfits.open(rrhrfile)
	hdr0 = hdulist0[0].header
	hdulist0.close

	hdr0.update(key='expstart',value=hdr1['expstart'])
	hdr0.update(key='expend',value=hdr1['expend'])
	hdr0.update(key='exptime',value=hdr1['exptime'])

	rr = get_fits_data(rrfile)

	rrhr = scipy.ndimage.interpolation.zoom(rr,4.,order=0,prefilter=False)
	pyfits.writeto(outfile,rrhr,hdr0,clobber=True)

	return

def write_int(cntfile,rrhrfile,oldint,outfile):
	"""Writes out an intensity (int) map given a count (cnt) and a high resolution relative response (rrhr)."""
	cnt  = get_fits_data(cntfile)
	rrhr = get_fits_data(rrhrfile)

	hdulist1 = pyfits.open(cntfile)
	hdr1 = hdulist1[0].header
	hdulist1.close

	hdulist0 = pyfits.open(oldint)
	hdr0 = hdulist0[0].header
	hdulist0.close

	hdr0.update(key='expstart',value=hdr1['expstart'])
	hdr0.update(key='expend',value=hdr1['expend'])
	hdr0.update(key='exptime',value=hdr1['exptime'])

	int = cnt/rrhr
	int[np.where(np.isnan(int)==True)]=0.

	pyfits.writeto(outfile,int,hdr0,clobber=True)

	return
