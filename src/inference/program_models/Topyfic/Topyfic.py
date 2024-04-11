import os
import gin
import argparse

import mudata
import anndata

import Topyfic


# NOTE: _template_env.yml contains the essential pacakges that must be present
# in your conda env. Add more packages as neccessary.

# Write a function to run your method

# Most parameters of this function will be supplied by the user 
# using a gin-config file. Generally those should include
# all the user tunable parameters specific for this method.
# Read more here https://github.com/google/gin-config/blob/master/docs/index.md

# Other general parameters such as number of workers etc.
# are supplied separately as they will be common in the 
# pipeline that will use these functions.
# Replace name with run_{program_inference_method}_

# Topyfic described -> https://github.com/mortazavilab/Topyfic
import pandas as pd


def run_Topyfic_train(adata,
                      k,
                      name='Topyfic',
                      n_runs=100,
                      random_state_range=None,
                      learning_method="online",
                      batch_size=1000,
                      max_iter=10,
                      n_jobs=None,
                      n_thread=1,
                      output_dir="",
                      **kwargs):
    train = Topyfic.Train(name=name,
                          k=k,
                          n_runs=n_runs,
                          random_state_range=random_state_range)

    train.run_LDA_models(adata, learning_method=learning_method, batch_size=batch_size,
                         max_iter=max_iter, n_jobs=n_jobs, n_thread=n_thread, **kwargs)

    train.save_train(save_path=output_dir)

    return train


def run_Topyfic_topmodel(adata,
                         trains,
                         n_top_genes=50,
                         resolution=1,
                         max_iter_harmony=10,
                         min_cell_participation=None,
                         file_format='pdf',
                         output_dir=""):
    top_model, clustering, adata = Topyfic.calculate_leiden_clustering(trains=trains,
                                                                       data=adata,
                                                                       n_top_genes=n_top_genes,
                                                                       resolution=resolution,
                                                                       max_iter_harmony=max_iter_harmony,
                                                                       min_cell_participation=min_cell_participation,
                                                                       file_format=file_format)

    top_model.save_topModel(save_path=output_dir)

    analysis_top_model = Topyfic.Analysis(Top_model=top_model)
    analysis_top_model.calculate_cell_participation(data=adata)
    analysis_top_model.save_analysis(save_path=output_dir)

    return top_model, analysis_top_model, clustering, adata


@gin.configurable
def run_Topyfic_(adata,
                 layer='X',
                 n_topics=15,
                 name='Topyfic',
                 n_runs=100,
                 random_state_range=None,
                 learning_method="online",
                 batch_size=1000,
                 max_iter=10,
                 n_jobs=None,
                 n_thread=1,
                 n_top_genes=50,
                 resolution=1,
                 max_iter_harmony=10,
                 min_cell_participation=None,
                 file_format='pdf',
                 output_dir="",
                 **kwargs):
    # Write code to run your method
    # You can write additional functions in this script
    # Or create more complex scripts in the scripts folder
    # and import the functions 

    # Place any imports that will only be present
    # in the method env (_template_env.yml) inside
    # this function

    adata = anndata.AnnData(adata.layers[layer], obs=adata.obs, var=adata.var)

    train = run_Topyfic_train(adata,
                              k=n_topics,
                              name=name,
                              n_runs=n_runs,
                              random_state_range=random_state_range,
                              learning_method=learning_method,
                              batch_size=batch_size,
                              max_iter=max_iter,
                              n_jobs=n_jobs,
                              n_thread=n_thread,
                              output_dir=output_dir,
                              **kwargs)

    top_model, analysis_top_model, clustering, adata = run_Topyfic_topmodel(adata,
                                                                            trains=[train],
                                                                            n_top_genes=n_top_genes,
                                                                            resolution=resolution,
                                                                            max_iter_harmony=max_iter_harmony,
                                                                            min_cell_participation=min_cell_participation,
                                                                            file_format=file_format,
                                                                            output_dir=output_dir)

    return train, top_model, analysis_top_model


# Use this function to store method outputs in the relevant
# mudata keys. This function will load the gin config file
# and call the previous function. Add parameters as neccessary
# but use the named parameters in the parser as they relate
# to the keys specified in our mudata input/output specification
# Replace name with run_{program_inference_method}
def run_program_inference_method(mdata,
                                 work_dir=None,
                                 prog_key='program_inference_method',
                                 data_key='rna',
                                 layer='X',
                                 config_path=None,
                                 inplace=True):
    """
    Perform gene program inference using {inference_method}.

    ARGS:
        mdata : MuData
            mudata object containing anndata of data and cell-level metadata.
        work_dir: str
            path to directory to store outputs.
        prog_key: 
            index for the anndata object (mdata[prog_key]) in the mudata object.
        data_key: str
            index of the genomic data anndata object (mdata[data_key]) in the mudata object.
        layer: str (default: X)
            anndata layer (mdata[data_key].layers[layer]) where the data is stored.
        config_path: str
            path to gin configurable config file containing method specific parameters.
        inplace: Bool (default: True)
            update the mudata object inplace or return a copy

    RETURNS:
        if not inplace:
            mdata
    
    """

    # Load method specific parameters
    try:
        gin.parse_config_file(config_path)
    except:
        raise ValueError('gin config file could not be found')

    if not inplace:
        mdata = mudata.MuData({data_key: mdata[data_key].copy()})

    # Create output directory for cNMF results
    if work_dir is not None:
        try:
            os.makedirs(work_dir, exist_ok=True)
        except:
            raise ValueError('Work directory location does not exist.')

    # Compute (structure this as neccessary)
    # Not that method specific params loaded via gin do not
    # have to be passed explicity
    train, top_model, analysis_top_model = \
        run_Topyfic_(mdata[data_key],
                     layer=layer,
                     output_dir=work_dir)

    cell_program_scores = top_model.get_gene_weights().T
    cell_topic_participation = analysis_top_model.cell_participation
    cell_topic_participation.var = pd.concat([cell_topic_participation.var, cell_program_scores], axis=1)

    # Store cell x program and program x feature matrices
    mdata.mod[prog_key] = cell_topic_participation

    if not inplace:
        return mdata


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('mudataObj_path')
    parser.add_argument('--work_dir', default='./', type=str)
    parser.add_argument('-pk', '--prog_key', default='program_inference_method', typ=str)
    parser.add_argument('-dk', '--data_key', default='rna', typ=str)  # could be atac
    parser.add_argument('--layer', default='X', type=str)  # layer of data anndata to use for inference
    parser.add_argument('--config_path', default='./Topyfic_config.gin', type=str)
    parser.add_argument('--output', action='store_false')

    args = parser.parse_args()

    mdata = mudata.read(args.mudataObj_path)
    run_program_inference_method(mdata,
                                 work_dir=args.work_dir,
                                 prog_key=args.prog_key,
                                 data_key=args.data_key,
                                 layer=args.layer,
                                 config_path=args.config_path,
                                 inplace=args.output)
