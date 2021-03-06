# -*- mode: Python; indent-tabs-mode: nil -*-  #

import awe

import numpy as np
import sys
import os



#-----Simulation Default Values-----
iterations = 5
nwalkers   = 4
nstates    = 100
restarts   = float('inf')
maxreps    = 50

#-----WQ Default Values-----
wq_port = 9123
wq_fast_abort_multiplier = -1.0

#-----Get user options-----
def getopts():
        import optparse
        p = optparse.OptionParser()

        # AWE params
        p.add_option('-i', '--iterations', metavar="<int>", default=iterations, type=int, dest='iterations',
                     help='Number of AWE iterations (default=%s)' % iterations)
        p.add_option('-r', '--restarts', metavar="<int>", default=restarts, type=int, dest='restarts',
                     help='Number of times to restart a failed task (default=%s)' % restarts)
        p.add_option('-R', '--maxreps', metavar="<int>", default=maxreps, type=int, dest='maxreps',
                     help='Number of times to replicate a task (default=%s)' % maxreps)

        # WQ params
        p.add_option('-p', '--port', metavar="<int>", default=wq_port, type=int, dest='port',
                     help='Port for Work Queue to use (default=%s)' % wq_port)
        p.add_option('-n', '--name', metavar="<string>", default=None, type="string", dest='name',
                     help='A project name to use with the catalog server (default=standalone mode)')
        p.add_option('-f', '--fastabort', metavar="<float>", default=wq_fast_abort_multiplier, type=float, dest='fastabort',
                     help='Set the Work Queue fast abort multipler')
        p.add_option('-M', '--monitor', default=False, dest='enable_monitor', action='store_true',
                     help='Enable monitoring of resource usage of tasks (default=disabled)')
        p.add_option('-S', '--summaryfile', metavar="<file>", default=None, type="string", dest='summaryfile',
                     help='Print resource usage summary of tasks to <file>. Must be used with -M option. (default=wq-<pid>-resource-usage)')
        p.add_option('-d', '--debug', metavar="<string>", default=None, type="string", dest='debug', 
                     help='Print Work Queue debug messages')

        opts, args = p.parse_args()

        return opts


#-----Main Program------
if __name__ == "__main__":

        opts = getopts()

        cfg           = awe.workqueue.Config()
        cfg.fastabort = opts.fastabort
        cfg.restarts  = opts.restarts
        cfg.maxreps   = opts.maxreps
        cfg.name      = opts.name
        cfg.port      = opts.port
	
        if opts.debug:
                cfg.debug = opts.debug 

        if opts.enable_monitor:
                cfg.monitor = True 
                cfg.summaryfile = opts.summaryfile

        # The "main" function of the worker
        cfg.execute('awe-instance-data/execute-task.sh')

        # Binaries to run MD and assignment steps
        cfg.cache('awe-generic-data/binaries/$OS-$ARCH/pdb2gmx')
        cfg.cache('awe-generic-data/binaries/$OS-$ARCH/grompp')
        cfg.cache('awe-generic-data/binaries/$OS-$ARCH/mdrun')
        cfg.cache('awe-generic-data/binaries/$OS-$ARCH/awe-assign')

        cfg.cache('awe-generic-data/gmxtopologies')         # required for running gromacs for MD
        cfg.cache('awe-instance-data/sim.mdp')              # Gromacs simulation parameters
        cfg.cache('awe-instance-data/env.sh')               # setting up the worker execution environment
        cfg.cache('awe-instance-data/cells.dat')            # cell definitions
        cfg.cache('awe-instance-data/CellIndices.dat')      # cell atoms to use when assigning
        cfg.cache('awe-instance-data/StructureIndices.dat') # walker atoms to use when assigning

        # initialize the weights randomly
        weights   = np.random.random((nstates,nwalkers))
        weights  /= np.sum(weights.flatten())

        # load a topology file
        system    = awe.System(topology = awe.PDB('awe-instance-data/topol.pdb'))

        # 2-color awe needs states assigned to a region
        partition = awe.SinkStates()
        partition.add(0, *range(0,nstates//2))
        partition.add(1, *range(nstates//2,nstates))

        # load the initial cells and walkers
        srcdir = 'awe-instance-data/pdbs/ala'
        for i in range(nstates):

            if i < nstates // 3:
                cell = awe.Cell(i, core=0)
            elif i > 2 * nstates // 3:
                cell = awe.Cell(i, core=1)
            else:
                cell = awe.Cell(i)

            color = partition.color(cell)
            system.add_cell(cell)


            for j in range(nwalkers):

                pdbpath = os.path.join(srcdir, 'State%d-%d.pdb' % (i, j))
                pdb     = awe.PDB(pdbpath)
                w       = awe.Walker(start=pdb.coords, assignment=i, color=color, weight=weights[i,j], cellid=cell.id)
                system.add_walker(w)

        # define the AWE resampling algorithm to use
        multicolor = awe.resample.MultiColor(nwalkers, partition)
        resample   = awe.resample.SaveWeights(multicolor)
        adaptive   = awe.AWE( wqconfig   = cfg,
			      system     = system,
			      iterations = opts.iterations,
			      resample   = resample,
			      checkpointfreq = 1,
                  verbose=True,
                  log_it=True)

        adaptive.run()

        print('Run time:', awe.time.time(), 's')
        sys.exit(0)
