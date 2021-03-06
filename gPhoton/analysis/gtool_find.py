__version__ = '1.0'

"""
.. module:: gtool_find

   :synopsis: Given a gTarget state file, will execute gFind to 
   determine the exposure time information for the given target.  Serves
   as a wrapper to gFind itself.  Also does some additional calculations
   to convert reported GALEX times into JD and Gregorian dates and times
   .

.. moduleauthor:: Scott W. Fleming <fleming@stsci.edu>
"""

import argparse
import numpy as np
import os
from gtool_read import read as gt_read
from gtool_write import update as gt_update
from gtool_utils import (calculate_jd as calc_jd, 
                         calculate_caldat as calc_caldat)

""" <DEVEL> Note that this hack to make it so that the user can import 
`stitch_components` directly as a module or run it from the command line
 as __main__ has the side effect of importing this module twice, despite
 my best efforts to work around it.  I don't think it will be a major 
issue, but worth thinking about in the future. </DEVEL> """
if __package__ is None:
    import sys, os
    gtfind_dir = os.path.dirname(os.path.abspath(__file__))
    gtfind_pardir = os.path.dirname(gtfind_dir)
    sys.path.insert(1, gtfind_pardir)
    from gFind import (gFind, setup_parser as gf_setup_parser, 
                       check_args as gf_check_args)

""" These module-level variables ensure both the ArgumentParser and 
module use the same defaults. """
#--------------------
ifile_default = None
#--------------------

#--------------------
def setup_args():
    """
    Set up command-line arguments and options.

    :returns: ArgumentParser -- Stores arguments and options.
    """
    parser = argparse.ArgumentParser(description="""Read in state files 
                                     for use with gtool_find.""")

    parser.add_argument("ifile", action="store", type=str, nargs='?',
                        default=ifile_default, 
                        help="""Full path and file name of the input 
                        state file.""")

    parser.add_argument("--no_overwrite", action="store_true", 
                        help="Only update gFind results if no previous "
                        "results are in the StateFile.")
    return parser
#--------------------

#--------------------
def check_input_options(args):
    """
    Check that input arguments satisfy some minimum requirements.

    :param args: Stored arguments and options.

    :type args: argparse.Namespace object.

    :raises: IOError
    """

    """ Make sure the input file exists. """
    if args.ifile is not None:
        if not os.path.isfile(args.ifile):
            raise IOError("State file not found.  Looking for " + 
                          args.ifile)
#--------------------

#--------------------
def gtool_find(args, ifile=ifile_default):
    """
    Reads in the state file and executes a gFind command to obtain
    exposure time information.  Updates the state file with this 
    information.

    :param args: Command-line input options.

    :type args: dict
    
    :param ifile: Input state file, it will also be the file that is
    updated with the results of the gFind query.

    :type ifile: str

    :raises: IOError
    """

    """ Read in the state file. """
    if ifile is not None:
        state_file_content = gt_read(ifile)
    else:
        raise IOError("You must specify an input file.")

    """ Test call of gFind. """
    exptime_data = gFind(band=args["band"], detsize=args["detsize"], 
                         exponly=False, gaper=args["gaper"], 
                         maxgap=args["maxgap"], minexp=args["minexp"],
                         quiet=True, retries=args["retries"], 
                         skypos=[state_file_content.ra, 
                                              state_file_content.dec],
                         trange=args["trange"], verbose=args["verbose"],
                         predicted=False)

    """ Update the total exposure time in the file. """
    if "FUV" in exptime_data and (not args["no_overwrite"] or 
                                  state_file_content.fuv_tot_exptime 
                                  is None):
        state_file_content.fuv_tot_exptime = exptime_data["FUV"]["expt"]
    if "NUV" in exptime_data and (not args["no_overwrite"] or 
                                  state_file_content.nuv_tot_exptime 
                                  is None):
        state_file_content.nuv_tot_exptime = exptime_data["NUV"]["expt"]

    """ Update the start and end times of the entire range. """
    if "FUV" in exptime_data and (not args["no_overwrite"] or
                                  state_file_content.fuv_timerange_start
                                  is None or 
                                  state_file_content.fuv_timerange_end 
                                  is None):
        state_file_content.fuv_timerange_start = np.nanmin(
            exptime_data["FUV"]["t0"])
        state_file_content.fuv_timerange_end = np.nanmax(
            exptime_data["FUV"]["t1"])
    if "NUV" in exptime_data and (not args["no_overwrite"] or
                                  state_file_content.nuv_timerange_start
                                  is None or 
                                  state_file_content.nuv_timerange_end 
                                  is None):
        state_file_content.nuv_timerange_start = np.nanmin(
            exptime_data["NUV"]["t0"])
        state_file_content.nuv_timerange_end = np.nanmax(
            exptime_data["NUV"]["t1"])

    """ Add an array of (start,stop) times. """
    if "FUV" in exptime_data and (not args["no_overwrite"] or 
                                  state_file_content.fuv_start_stop 
                                  is None):
        fuv_start_stop = [(x,y,calc_jd(x),calc_jd(y),calc_caldat(x),
                           calc_caldat(y),y-x) 
                          for x,y in zip(
                exptime_data["FUV"]["t0"], 
                exptime_data["FUV"]["t1"],
                )]
        state_file_content.fuv_start_stop = fuv_start_stop
    if "NUV" in exptime_data and (not args["no_overwrite"] or 
                                  state_file_content.nuv_start_stop 
                                  is None):
        nuv_start_stop = [(x,y,calc_jd(x),calc_jd(y),calc_caldat(x),
                           calc_caldat(y),y-x) 
                          for x,y in zip(
                exptime_data["NUV"]["t0"], 
                exptime_data["NUV"]["t1"],
                )]
        state_file_content.nuv_start_stop = nuv_start_stop
    
    """ Update the JSON file on disk. """
    gt_update(state_file_content, ifile)
#--------------------

#--------------------
if __name__ == "__main__":
    """ Create ArgumentParser object that holds arguments and 
    options. """
    parser = setup_args()

    """ Add the keywords from the main gFind method. """
    parser = gf_setup_parser(parser=parser)

    """ Parse all the input arguments. """
    args = parser.parse_args()

    """ Check arguments and options.  Use both this module's checker 
    and the main gFind method. """
    check_input_options(args)
    args = gf_check_args(args, allow_no_coords=True)

    """ Call primary method. """
    gtool_find(vars(args), args.ifile)
#--------------------


