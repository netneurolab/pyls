# -*- coding: utf-8 -*-

import warnings
import numpy as np
from ..base import BasePLS
from ..structures import _pls_input_docs
from .. import compute, utils


class MeanCenteredPLS(BasePLS):
    def __init__(self, X, groups=None, n_cond=1, mean_centering=0, n_perm=5000,
                 n_boot=5000, n_split=100, test_size=0.25, rotate=True, ci=95,
                 seed=None, verbose=True, **kwargs):
        if groups is None:
            groups = [len(X) // n_cond]
        # check inputs for validity
        if n_cond == 1 and len(groups) == 1:
            raise ValueError('Cannot perform PLS with only one group and one '
                             'condition. Please confirm inputs are correct.')
        if n_cond == 1 and mean_centering == 0:
            warnings.warn('Cannot set mean_centering to 0 when there is only'
                          'one condition. Resetting mean_centering to 1.')
            mean_centering = 1
        elif len(groups) == 1 and mean_centering == 1:
            warnings.warn('Cannot set mean_centering to 1 when there is only '
                          'one group. Resetting mean_centering to 0.')
            mean_centering = 0

        # instantiate base class, generate dummy array, and run PLS analysis
        super().__init__(X=X, groups=groups, n_cond=n_cond,
                         mean_centering=mean_centering, n_perm=n_perm,
                         n_boot=n_boot, n_split=n_split, test_size=test_size,
                         rotate=rotate, ci=ci, seed=seed, verbose=verbose,
                         **kwargs)
        self.inputs.Y = utils.dummy_code(self.inputs.groups,
                                         self.inputs.n_cond)
        self.results = self.run_pls(np.asarray(self.inputs.X), self.inputs.Y)

    def gen_covcorr(self, X, Y, **kwargs):
        """
        Computes mean-centered matrix from `X` and `Y`

        Parameters
        ----------
        X : (S, B) array_like
            Input data matrix, where `S` is observations and `B` is features
        Y : (S, T) array_like
            Dummy coded input array, where `S` is observations and `T`
            corresponds to the number of different groups x conditions. A value
            of 1 indicates that an observation belongs to a specific group or
            condition.

        Returns
        -------
        mean_centered : (T, B) np.ndarray
            Mean-centered matrix
        """

        mean_centered = compute.get_mean_center(X, Y,
                                                self.inputs.n_cond,
                                                self.inputs.mean_centering,
                                                means=True)
        return mean_centered

    def boot_distrib(self, X, Y, U_boot):
        """
        Generates bootstrapped distribution for contrast

        Parameters
        ----------
        X : (S, B) array_like
            Input data matrix, where `S` is observations and `B` is features
        Y : (S, T) array_like
            Dummy coded input array, where `S` is observations and `T`
            corresponds to the number of different groups x conditions. A value
            of 1 indicates that an observation belongs to a specific group or
            condition.
        U_boot : (B, L, R) array_like
            Bootstrapped values of the right singular vectors, where `B` is the
            same as in `X`, `L` is the number of latent variables and `R` is
            the number of bootstraps


        Returns
        -------
        distrib : (T, L, R) np.ndarray
        """

        distrib = np.zeros(shape=(Y.shape[-1], U_boot.shape[1],
                                  self.inputs.n_boot,))

        for i in utils.trange(self.inputs.n_boot, desc='Calculating CI'):
            boot, U = self.bootsamp[:, i], U_boot[:, :, i]
            usc = compute.get_mean_center(X[boot], Y,
                                          self.inputs.n_cond,
                                          self.inputs.mean_centering,
                                          means=False) @ compute.normalize(U)
            distrib[:, :, i] = np.row_stack([usc[grp].mean(axis=0) for grp
                                             in Y.T.astype(bool)])

        return distrib

    def run_pls(self, X, Y):
        """
        Runs PLS analysis

        Parameters
        ----------
        X : (S, B) array_like
            Input data matrix, where `S` is observations and `B` is features
        Y : (S, T) array_like, optional
            Dummy coded input array, where `S` is observations and `T`
            corresponds to the number of different groups x conditions. A value
            of 1 indicates that an observation belongs to a specific group or
            condition.
        """

        res = super().run_pls(X, Y)
        res.brainscores, res.designscores = X @ res.u, Y @ res.v

        # get normalized brain scores and contrast
        usc2 = compute.get_mean_center(X, Y,
                                       self.inputs.n_cond,
                                       self.inputs.mean_centering,
                                       means=False) @ res.u
        orig_usc = np.row_stack([usc2[grp].mean(axis=0) for grp
                                 in Y.T.astype(bool)])
        res.brainscores_dm = usc2

        if self.inputs.n_boot > 0:
            # compute bootstraps and BSRs
            U_boot, V_boot = self.bootstrap(X, Y)
            compare_u, u_se = compute.boot_rel(res.u @ res.s, U_boot)

            # generate distribution / confidence intervals for contrast
            distrib = self.boot_distrib(X, Y, U_boot)
            llusc, ulusc = compute.boot_ci(distrib, ci=self.inputs.ci)

            # update results.boot_result dictionary
            res.bootres.update(dict(bootstrapratios=compare_u,
                                    uboot_se=u_se,
                                    bootsamples=self.bootsamp,
                                    contrast=orig_usc,
                                    contrast_boot=distrib,
                                    contrast_lolim=llusc,
                                    contrast_uplim=ulusc))

        # get rid of the stupid diagonal matrix
        res.s = np.diag(res.s)

        return res


def meancentered_pls(X, *, groups=None, n_cond=1, mean_centering=0,
                     n_perm=5000, n_boot=5000, n_split=100, test_size=0.25,
                     rotate=True, ci=95, seed=None, verbose=True, **kwargs):
    pls = MeanCenteredPLS(X=X, groups=groups, n_cond=n_cond,
                          mean_centering=mean_centering,
                          n_perm=n_perm, n_boot=n_boot, n_split=n_split,
                          test_size=test_size, rotate=rotate, ci=ci, seed=seed,
                          verbose=verbose, **kwargs)
    return pls.results


meancentered_pls.__doc__ = r"""\
Performs mean-centered PLS on `X`, sorted into `groups` and `conditions`.

Mean-centered PLS is a multivariate statistical approach that attempts to
find sets of variables in a matrix which maximally discriminate between
subgroups within the matrix.

While it carries the name PLS, mean-centered PLS is perhaps more related to
principal components analysis than it is to :obj:`pyls.behavioral_pls`. In
contrast to behavioral PLS, mean-centered PLS does not construct a cross-
covariance matrix. Instead, it operates by averaging the provided data
(`X`) within groups and/or conditions. The resultant matrix :math:`M` is
mean-centered, generating a new matrix :math:`R_{{mean\_centered}}` which
is submitted to singular value decomposition.

Parameters
----------
{input_matrix}
{groups}
{conditions}
{mean_centering}
{stat_test}
{rotate}
{ci}
{seed}
{verbose}

Returns
----------
{pls_results}

Notes
-----
The provided `mean_centering` argument can be changed to highlight or
"boost" potential group / condition differences by modfiying how
:math:`R_{{mean\_centered}}` is generated:

- `mean_centering=0` will remove group means collapsed across conditions,
  emphasizing potential differences between conditions while removing
  overall group differences
- `mean_centering=1` will remove condition means collapsed across groups,
  emphasizing potential differences between groups while removing overall
  condition differences
- `mean_centering=2` will remove the grand mean collapsed across both
  groups _and_ conditions, permitting investigation of the full spectrum of
  potential group and condition effects.

{decomposition_narrative}

References
----------
{references}
""".format(**_pls_input_docs)
