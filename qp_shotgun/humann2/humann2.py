# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from os.path import basename, join

from future.utils import viewitems

from qiita_client.util import system_call, get_sample_names_by_run_prefix


def generate_humann2_analysis_commands(forward_seqs, reverse_seqs, map_file,
                                       out_dir, parameters):
    """Generates the HUMAnN2 commands

    Parameters
    ----------
    forward_seqs : list of str
        The list of forward seqs filepaths
    reverse_seqs : list of str
        The list of reverse seqs filepaths
    map_file : str
        The path to the mapping file
    out_dir : str
        The job output directory
    parameters : dict
        The command's parameters, keyed by parameter name

    Returns
    -------
    list of str
        The HUMAnN2 commands

    Raises
    ------
    ValueError
        If the rev is not an empty list and the same length than fwd seqs
        The prefixes of the run_prefix don't match the file names

    Notes
    -----
    The forward and reverse files are going to have different filenames but
    the sample name is going to be the same so the results are merged when
    joining the outputs
    """
    # making sure the forward and reverse reads are in the same order
    forward_seqs.sort()
    if reverse_seqs:
        if len(forward_seqs) != len(reverse_seqs):
            raise ValueError('Your reverse and forward files are of different '
                             'length. Forward: %s. Reverse: %s.' %
                             (', '.join(forward_seqs),
                              ', '.join(reverse_seqs)))
        reverse_seqs.sort()

    sn_by_rp = get_sample_names_by_run_prefix(map_file)

    # we match sample name and forward filename
    samples = []
    for i, fname in enumerate(forward_seqs):
        f = basename(fname)
        # removing extentions: fastq or fastq.gz
        if 'fastq' in f.lower().rsplit('.', 2):
            f = f[:f.lower().rindex('.fastq')]
        # this try/except block is simply to retrieve all possible errors
        # and display them in the next if block
        try:
            samples.append((fname, f, sn_by_rp[f]))
            if reverse_seqs:
                fr = basename(reverse_seqs[i])
                if 'fastq' in fr.lower().rsplit('.', 2):
                    fr = fr[:fr.lower().rindex('.fastq')]
                samples.append((reverse_seqs[i], fr, sn_by_rp[f]))
            del sn_by_rp[f]
        except KeyError:
            pass

    if sn_by_rp:
        raise ValueError(
            'Some run_prefix values do not match your sample names: %s'
            % ', '.join(sn_by_rp.keys()))

    cmds = []
    params = ['--%s "%s"' % (k, v) for k, v in viewitems(parameters) if v]
    for ffn, fn, s in samples:
        cmds.append('humann2 --input "%s" --output "%s" --output-basename '
                    '"%s" --output-format biom %s' % (ffn, join(out_dir, fn),
                                                      s, ' '.join(params)))

    return cmds


def humann2(qclient, job_id, parameters, out_dir):
    """Run humann2 with the given parameters

    Parameters
    ----------
    qclient : tgp.qiita_client.QiitaClient
        The Qiita server client
    job_id : str
        The job id
    parameters : dict
        The parameter values to run split libraries
    out_dir : str
        Yhe path to the job's output directory

    Returns
    -------
    boolean, list, str
        The results of the job
    """
    # Step 1 get the rest of the information need to run humann2
    qclient.update_job_step(job_id, "Step 1 of 5: Collecting information")
    artifact_id = parameters['input']
    # removing input from parameters so it's not part of the final command
    del parameters['input']

    # Get the artifact filepath information
    artifact_info = qclient.get("/qiita_db/artifacts/%s/" % artifact_id)
    fps = artifact_info['files']

    # Get the artifact metadata
    prep_info = qclient.get('/qiita_db/prep_template/%s/'
                            % artifact_info['prep_information'][0])
    qiime_map = prep_info['qiime-map']

    # Step 2 generating command humann2
    qclient.update_job_step(job_id, "Step 2 of 5: Generating HUMANn2 command")
    if 'raw_reverse_seqs' in fps:
        rs = fps['raw_reverse_seqs']
    else:
        rs = []
    commands = generate_humann2_analysis_commands(fps['raw_forward_seqs'], rs,
                                                  qiime_map, out_dir,
                                                  parameters)

    # Step 3 execute humann2
    commands_len = len(commands)
    for i, cmd in enumerate(commands):
        qclient.update_job_step(job_id, "Step 3 of 5: Executing HUMANn2"
                                ", job %d/%d" % (i, commands_len))
        std_out, std_err, return_value = system_call(cmd)
        if return_value != 0:
            error_msg = ("Error running HUMANn2:\nStd out: %s\nStd err: %s"
                         % (std_out, std_err))
            return False, None, error_msg

    # Step 4 merge tables
    qclient.update_job_step(job_id, "Step 4 of 5: Merging resulting tables")

    # Step 5 generating re-normalized tables: TODO
    qclient.update_job_step(job_id, "Step 5 of 5: Re-normalizing tables")
    artifacts_info = []

    return True, artifacts_info, ""
