#!/usr/bin/env python

"""
Sensory integration model demo.

Notes
-----
Set integration module neuron parameters by running ./data/create_int_gexf.py
Generate input files by running ./data/gen_olf_input.py and ./data/gen_vis_input.py
"""

import argparse
import itertools

import networkx as nx

nx.readwrite.gexf.GEXF.convert_bool = {'false':False, 'False':False,
                                       'true':True, 'True':True}
import neurokernel.core as core
import neurokernel.base as base
import neurokernel.tools.graph as graph_tools
from neurokernel.tools.comm import get_random_port

import neurokernel.pattern as pattern
from neurokernel.LPU.LPU import LPU
import data.vision_configuration as vc
from time import time


def print_time(tic = 0., s = None):
    if s is not None:
        print "%s: %f" % (s, time()-tic)
    return time()

parser = argparse.ArgumentParser()
parser.add_argument('--debug', default=False,
                    dest='debug', action='store_true',
                    help='Write connectivity structures and inter-LPU routed data in debug folder')
parser.add_argument('-l', '--log', default='none', type=str,
                    help='Log output to screen [file, screen, both, or none; default:none]')
parser.add_argument('-s', '--steps', default=14000, type=int,
                    help='Number of steps [default:14000]')
parser.add_argument('-d', '--port_data', default=None, type=int,
                    help='Data port [default:randomly selected]')
parser.add_argument('-c', '--port_ctrl', default=None, type=int,
                    help='Control port [default:randomly selected]')
parser.add_argument('-t', '--port_time', default=None, type=int,
                    help='Timing port [default: randomly selected]')
parser.add_argument('-r', '--time_sync', default=False, action='store_true',
                    help='Time data reception throughput [default: False]')
parser.add_argument('-b', '--lam_dev', default=0, type=int,
                    help='GPU for lamina lobe [default:0]')
parser.add_argument('-m', '--med_dev', default=1, type=int,
                    help='GPU for medulla [default:1]')
parser.add_argument('-a', '--al_dev', default=2, type=int,
                    help='GPU for antennal lobe [default:2]')
parser.add_argument('-i', '--int_dev', default=3, type=int,
                    help='GPU for integration [default:3]')
parser.add_argument('-e', '--timeit', default=False, type=bool,
                    help='Time the script [default:False]')
args = parser.parse_args()

dt = 1e-4
dur = 1.4
Nt = args.steps or int(dur/dt)

file_name = 'neurokernel.log' if args.log.lower() in ['file', 'both'] else None
screen = True if args.log.lower() in ['screen', 'both'] else False
logger = base.setup_logger(file_name=file_name, screen=screen)

if args.port_data is None:
    port_data = get_random_port()
else:
    port_data = args.port_data
if args.port_ctrl is None:
    port_ctrl = get_random_port()
else:
    port_ctrl = args.port_ctrl
if args.port_time is None:
    port_time = get_random_port()
else:
    port_time = args.port_time

if args.timeit:
    ptime = lambda t, s: print_time(t, s)
else:
    ptime = lambda t, s: print_time(t)

man = core.Manager(port_data, port_ctrl, port_time)
man.add_brok()

tic = time()

# Load configurations for lamina, medulla and antennal lobe models:
(n_dict_al, s_dict_al) = LPU.lpu_parser( './data/antennallobe.gexf.gz')
lpu_al = LPU(dt, n_dict_al, s_dict_al,
             input_file='./data/olfactory_input.h5',
             output_file='antennallobe_output.h5',
             port_ctrl=port_ctrl, port_data=port_data, port_time=port_time,
             device=args.al_dev, id='antennallobe', time_sync=args.time_sync)
man.add_mod(lpu_al)
tic = ptime(tic, 'Load AL LPU time')

(n_dict_lam, s_dict_lam) = LPU.lpu_parser('./data/lamina.gexf.gz')
lpu_lam = LPU(dt, n_dict_lam, s_dict_lam,
              input_file='./data/vision_input.h5',
              output_file='lamina_output.h5',
              port_ctrl=port_ctrl, port_data=port_data, port_time=port_time,
              device=args.al_dev, id='lamina', time_sync=args.time_sync)
man.add_mod(lpu_lam)
tic = ptime(tic, 'Load LAM LPU time')

(n_dict_med, s_dict_med) = LPU.lpu_parser('./data/medulla.gexf.gz')
lpu_med = LPU(dt, n_dict_med, s_dict_med,
              output_file='medulla_output.h5',
              port_ctrl=port_ctrl, port_data=port_data, port_time=port_time,
              device=args.al_dev, id='medulla', time_sync=args.time_sync)
man.add_mod(lpu_med)
tic = ptime(tic, 'Load MED LPU time')

(n_dict_int, s_dict_int) = LPU.lpu_parser('./data/integrate.gexf.gz')
lpu_int = LPU(dt, n_dict_int, s_dict_int,
              output_file='integrate_output.h5',
              port_ctrl=port_ctrl, port_data=port_data, port_time=port_time,
              device=args.al_dev, id='integrate', time_sync=args.time_sync)
man.add_mod(lpu_int)
tic = ptime(tic, 'Load INT LPU time')

# connect lam to med
pat_lam_med = vc.create_pattern(lpu_lam, lpu_med)

man.connect(lpu_lam, lpu_med, pat_lam_med, 0, 1)
tic = ptime(tic, 'Connect LAM and MED time')

intf_al = lpu_al.interface
intf_lam = lpu_lam.interface
intf_med = lpu_med.interface
intf_int = lpu_int.interface

# Initialize connectivity patterns among LPU's
pat_al_int = pattern.Pattern(','.join(intf_al.to_selectors()),
                             ','.join(intf_int.to_selectors()))
pat_med_int = pattern.Pattern(','.join(intf_med.to_selectors()),
                              ','.join(intf_int.to_selectors()))

# Create connections from antennal lobe to integration LPU
for src, dest in zip(['/al[0]/pn%d' % i for i in xrange(3)],
        intf_int.in_ports().spike_ports().to_selectors()):
        pat_al_int[src, dest] = 1
        pat_al_int.interface[src, 'type'] = 'spike'
        pat_al_int.interface[dest, 'type'] = 'spike'

# Create connections from medulla to integration LPU
for src, dest in zip(['/medulla/Mt3%c[%d]' % (c, i) for c in ('h','v') for i in xrange(4)],
                     intf_int.in_ports().gpot_ports().to_selectors()):
    pat_med_int[src, dest] = 1
    pat_med_int.interface[src, 'type'] = 'gpot'
    pat_med_int.interface[dest, 'type'] = 'gpot'

man.connect(lpu_al, lpu_int, pat_al_int, 0, 1)
man.connect(lpu_med, lpu_int, pat_med_int, 0, 1)
tic = ptime(tic, 'Connect MED and AL to INT time')

man.start(steps=Nt)
man.stop()
tic = ptime(tic, 'Run Simulation time')
