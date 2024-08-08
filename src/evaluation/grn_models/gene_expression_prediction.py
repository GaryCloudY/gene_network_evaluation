import os
import argparse

import mudata

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, Lasso, Ridge, ElasticNet, BayesianRidge
from sklearn.svm import LinearSVR
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.naive_bayes import GaussianNB
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor, BaggingRegressor
from sklearn.neighbors import KNeighborsRegressor

from joblib import Parallel, delayed
from tqdm.auto import tqdm


def _select_data(
    grn,        
    adata,
    target,
    source_key="tf",
    target_key="gene",
    layer=None,
    return_regulators=False
):
    sub_grn = grn[grn[target_key] == target]
    regulators = sub_grn[source_key].values
    regulator_idx = np.where(adata.var.index.isin(regulators))[0]
    target_idx = np.where(adata.var.index == target)[0]
    if layer is not None:
        if layer not in adata.layers.keys():
            raise ValueError(f"Layer {layer} not found in adata.")
        X = adata[:, regulator_idx].layers[layer].copy()
        y = adata[:, target_idx].layers[layer].copy()
    else:
        X = adata[:, regulator_idx].X.copy()
        y = adata[:, target_idx].X.copy()
    if hasattr(X, "toarray"):
        X = X.toarray()
    if hasattr(y, "toarray"):
        y = y.toarray()
    if len(y.shape) > 1:
        y = y.flatten()
    if return_regulators:
        return X, y, regulators
    else:
        return X, y


def _fit_model(
    grn, 
    adata,
    target,
    model=LinearRegression(),
    min_regulators=1,
    source_key="tf",
    target_key="gene",
    layer=None,
    verbose=True
):
    X, y, regulators = _select_data(grn, adata, target, source_key, target_key, layer, return_regulators=True)
    n_cells, n_regulators = X.shape
    if n_regulators < min_regulators:
        if verbose:
            print(f"Skipping {target} due to insufficient number of regulators: {n_regulators}")
        return None
    model.fit(X, y)
    r2 = model.score(X, y)
    mse = np.mean((model.predict(X) - y) ** 2)
    return {"target": target, "r2": r2, "mse": mse, "n_cells": n_cells, "regulators": regulators}


def _compute_gene_expression_prediction(
    grn,
    adata,
    model=LinearRegression(),
    min_regulators=1,
    source_key="tf",
    target_key="gene",
    layer=None,
    n_jobs=1,
    verbose=True,
):
    """
    Computes the proportion of variance in the data explained by each program.

    ARGS
        mdata : MuData
            mudata object containing anndata of program scores and cell-level metadata.
        grn_key: str
            index for the anndata object (mdata[grn_key]) in the mudata object.
        data_key: str
            index of the genomic data anndata object (mdata[data_key]) in the mudata object.
        model: sklearn.linear_model
            model to fit the gene expression prediction.
        min_regulators: int
            minimum number of regulators required to fit the model.
        n_jobs: int (default: 1)
            number of threads to run processes on.
        verbose: Bool (default: True)
            print progress.
        inplace: Bool (default: True)
            update the mudata object inplace or return a copy
       
    RETURNS 
        if not inplace:
            mdata[grn_key].var['explained_variance_ratio_{}'.format(layer)]
            
    """
    targets = grn[target_key].unique()
    
    results = Parallel(n_jobs=n_jobs)(
        delayed(_fit_model)(
            grn, adata, target, model, min_regulators, source_key, target_key, layer, verbose
        ) for target in tqdm(targets, disable=not verbose,
                             desc="Gene expression prediction", unit="targets")
    )
    
    results = [r for r in results if r is not None]
    results = pd.DataFrame(results)
    results["n_regulators"] = results["regulators"].apply(len)
    
    return results


def compute_gene_expression_prediction(
    mdata: mudata.MuData,
    grn_key: str = "grn",
    celltype: str = None,
    data_key: str = "rna",
    model=LinearRegression(),
    min_regulators=1,
    n_jobs=1,
    verbose=True,
    inplace=True,
):
    """
    Computes the proportion of variance in the data explained by each program.

    ARGS
        mdata : MuData
            mudata object containing anndata of program scores and cell-level metadata.
        grn_key: str
            index for the anndata object (mdata[grn_key]) in the mudata object.
        data_key: str
            index of the genomic data anndata object (mdata[data_key]) in the mudata object.
        model: sklearn.linear_model
            model to fit the gene expression prediction.
        min_regulators: int
            minimum number of regulators required to fit the model.
        n_jobs: int (default: 1)
            number of threads to run processes on.
        verbose: Bool (default: True)
            print progress.
        inplace: Bool (default: True)
            update the mudata object inplace or return a copy
       
    RETURNS 
        if not inplace:
            mdata[grn_key].var['explained_variance_ratio_{}'.format(layer)]
            
    """
    
    if not inplace:
        mdata = mudata.MuData({grn_key: mdata[grn_key].copy(),
                               data_key: mdata[data_key].copy()})
    
    grn = mdata[grn_key].copy()
    if celltype is not None:
        grn = grn.query("celltype == @celltype")
    adata = mdata[data_key].copy()
    targets = grn["target"].unique()
    
    results = Parallel(n_jobs=n_jobs)(
        delayed(_fit_model)(
            grn, adata, target, model, min_regulators, verbose
        ) for target in tqdm(targets, disable=not verbose,
                             desc="Gene expression prediction", unit="targets")
    )
    
    results = [r for r in results if r is not None]
    results = pd.DataFrame(results)
    
    if inplace:
        mdata.uns["gene_expression_prediction"] = results
    else:
        return results
    
    
if __name__=='__main__':
    parser = argparse.ArgumentParser()
    
    parser.add_argument("--mdata", type=str, help="Path to MuData object")
    parser.add_argument("--grn_key", type=str, default="grn", help="Key for GRN in MuData object")
    parser.add_argument("--celltype", type=str, default=None, help="Celltype to subset GRN")
    parser.add_argument("--data_key", type=str, default="rna", help="Key for data in MuData object")
    parser.add_argument("--min_regulators", type=int, default=1, help="Minimum number of regulators required to fit the model")
    parser.add_argument("--n_jobs", type=int, default=1, help="Number of threads to run processes on")
    parser.add_argument("--verbose", action="store_true", help="Print progress")
    parser.add_argument("--inplace", action="store_true", help="Update MuData object inplace")
    args = parser.parse_args()

    mdata = mudata.load(args.mdata)
    compute_gene_expression_prediction(
        mdata, 
        grn_key=args.grn_key, 
        celltype=args.celltype, 
        data_key=args.data_key, 
        min_regulators=args.min_regulators, 
        n_jobs=args.n_jobs, 
        verbose=args.verbose, 
        inplace=args.inplace
    )
    mdata.save(args.mdata)