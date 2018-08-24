#! /bin/python

import os
import sys
import json

import luigi
import nifty.tools as nt
import nifty.distributed as ndist

import cluster_tools.utils.volume_utils as vu
import cluster_tools.utils.function_utils as fu
from cluster_tools.cluster_tasks import SlurmTask, LocalTask, LSFTask


#
# Graph Tasks
#

class MapEdgeIdsBase(luigi.Task):
    """ MapEdgeIds base class
    """

    task_name = 'map_edge_ids'
    src_file = os.path.abspath(__file__)
    allow_retry = False

    # input volumes and graph
    graph_path = luigi.Parameter()
    scale = luigi.Parameter()
    dependency = luigi.TaskParameter()

    def requires(self):
        return self.dependency

    def run(self):
        # get the global config and init configs
        self.make_dirs()
        shebang, block_shape, roi_begin, roi_end = self.global_config_values()
        self.init(shebang)

        # load the watershed config
        config = self.get_task_config()

        # update the config with input and graph paths and keys
        # as well as block shape
        config.update({'graph_path': self.graph_path, 'block_shape': block_shape,
                       'scale': self.scale})

        # prime and run the job
        self.prepare_jobs(1, None, config)
        self.submit_jobs(1)

        # wait till jobs finish and check for job success
        self.wait_for_jobs()
        self.check_jobs(1)


class MapEdgeIdsLocal(MapEdgeIdsBase, LocalTask):
    """ MapEdgeIds on local machine
    """
    pass


class MapEdgeIdsSlurm(MapEdgeIdsBase, SlurmTask):
    """ MapEdgeIds on slurm cluster
    """
    pass


class MapEdgeIdsLSF(MapEdgeIdsBase, LSFTask):
    """ MapEdgeIds on lsf cluster
    """
    pass


#
# Implementation
#


def map_edge_ids(job_id, config_path):

    fu.log("start processing job %i" % job_id)
    fu.log("reading config from %s" % config_path)

    # get the config
    with open(config_path) as f:
        config = json.load(f)
    scale = config['scale']
    graph_path = config['graph_path']
    initial_block_shape = config['block_shape']
    n_threads = config['threads_per_job']

    factor = 2**scale
    block_shape = [factor * bs for bs in initial_block_shape]

    with vu.file_reader(graph_path) as f:
        shape = f.attrs['shape']
    blocking = nt.blocking(roiBegin=[0, 0, 0],
                           roiEnd=list(shape),
                           blockShape=block_shape)
    input_key = 'graph'
    block_prefix = 'sub_graphs/s%s/block_' % scale
    ndist.mapEdgeIdsForAllBlocks(graph_path, input_key,
                                 blockPrefix=block_prefix,
                                 numberOfBlocks=blocking.numberOfBlocks,
                                 numberOfThreads=n_threads)
    fu.log_job_success(job_id)


if __name__ == '__main__':
    path = sys.argv[1]
    assert os.path.exists(path), path
    job_id = int(os.path.split(path)[1].split('.')[0].split('_')[-1])
    map_edge_ids(job_id, path)
