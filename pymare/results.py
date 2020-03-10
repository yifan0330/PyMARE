"""Tools for representing and manipulating meta-regression results."""

import numpy as np
import pandas as pd
import scipy.stats as ss

try:
    import arviz as az
except:
    az = None

from .stats import q_profile


def _compute_beta_stats(beta, v, X, tau2, alpha=0.05):
    w = 1. / (v + tau2)
    se = np.sqrt(np.diag(np.linalg.pinv((X * w).T.dot(X))))
    z_se = ss.norm.ppf(1 - alpha / 2)
    z = beta / se

    return {
        'se': se,
        'ci_l': beta - z_se * se,
        'ci_u': beta + z_se * se,
        'z': z,
        'p': 1 - np.abs(0.5 - ss.norm.cdf(z)) * 2
    }


class MetaRegressionResults:
    """Container for results generated by PyMARE meta-regression estimators.

    Args:
        params (dict): A dictionary containing parameter estimates. Typically
            contains entries for at least 'beta' and 'tau^2'.
        dataset (`pymare.Dataset`): A Dataset instance containing the inputs
            to the estimator.
        estimator (`pymare.estimators.BaseEstimator`): The estimator used to
            produce the results.
        ci_method (str, optional): The method to use when generating confidence
            intervals for tau^2. Currently only 'QP' (Q-Profile) is supported.
        alpha (float, optional): alpha value defining the coverage of the CIs,
            where width = 1 - alpha. Defaults to 0.05.
    """
    def __init__(self, params, dataset, estimator=None, ci_method='QP',
                 alpha=0.05):
        self.params = {name: {'est': val} for name, val in params.items()}
        self.dataset = dataset
        self.estimator = estimator
        self.ci_method = ci_method
        self.alpha = alpha

    def __getitem__(self, key):
        """Provides item-based access to parameter results."""
        return self.params[key]

    def summary(self):
        pass

    def plot(self):
        pass

    def to_df(self):
        """Return a pandas DataFrame summarizing results."""
        fixed = self.params['beta'].copy()
        fixed['name'] = self.dataset.names
        fixed = pd.DataFrame(fixed)

        tau2 = pd.DataFrame(pd.Series(self.params['tau2'])).T
        tau2['name'] = 'tau^2'

        df = pd.concat([fixed, tau2], axis=0, sort=False, ignore_index=True)
        df = df.loc[:, ['name', 'est', 'se', 'z', 'p', 'ci_l', 'ci_u']]
        ci_l = 'ci_{:.6g}'.format(self.alpha / 2)
        ci_u = 'ci_{:.6g}'.format(1 - self.alpha / 2)
        df.columns = ['name', 'estimate', 'se', 'z-score', 'p-val', ci_l, ci_u]

        return df

    def compute_stats(self, ci_method=None, alpha=None):
        """Compute post-estimation stats (SE and CI).

        Args:
            ci_method (str): The method to use when generating confidence
                intervals for tau^2. Currently only 'QP' (Q-Profile) is
                supported.
            alpha (float, optional): alpha value defining the coverage of the
                CIs, where width = 1 - alpha. Defaults to 0.05.
        """
        if alpha is not None:
            self.alpha = alpha
        if ci_method is not None:
            self.ci_method = ci_method

        v, X = self.dataset.v, self.dataset.X
        beta = self.params['beta']['est']
        alpha = self.alpha
        # for estimators that don't need variances, we use the estimated sigma
        if v is None:
            v = self.params.get('sigma', {'est': 0})['est']
            v = np.ones((len(X), 1)) * v
        tau2 = self.params.get('tau2', {'est': 0})['est']

        # Stats for fixed effects
        fixed_stats = _compute_beta_stats(beta, v, X, tau2, alpha)
        self.params['beta'].update(fixed_stats)

        # CIs for tau^2 via Q-Profile method
        if 'tau2' in self.params:
            ci = q_profile(self.dataset.y, v, X, alpha)
            self.params['tau2'].update(ci)


class BayesianMetaRegressionResults:
    """Container for MCMC sampling-based PyMARE meta-regression estimators.

    Args:
        data (`StanFit4Model` or `InferenceData`): Either a StanFit4Model
            instanced returned from PyStan or an ArviZ InferenceData instance.
        dataset (`pymare.Dataset`): A Dataset instance containing the inputs
            to the estimator.
        ci (float, optional): Desired width of highest posterior density (HPD)
            interval. Defaults to 95%.
    """
    def __init__(self, data, dataset, ci=95.):
        if az is None:
            raise ValueError("ArviZ package must be installed in order to work"
                             " with the BayesianMetaRegressionResults class.")
        if data.__class__.__name__ == 'StanFit4Model':
            data = az.from_pystan(data)
        self.data = data
        self.dataset = dataset
        self.ci = ci

    def summary(self, include_theta=False, **kwargs):
        """Summarize the posterior estimates via ArviZ.

        Args:
            include_theta (bool, optional): Whether or not to include the
                estimated group-level means in the summary. Defaults to False.
            kwargs: Optional keyword arguments to pass onto ArviZ's summary().

        Returns:
            A pandas DataFrame, unless the `fmt="xarray"` argument is passed in
            kwargs, in which case an xarray Dataset is returned.
        """
        var_names = ['beta', 'tau2']
        if include_theta:
            var_names.append('theta')
        var_names = kwargs.pop('var_names', var_names)
        return az.summary(self.data, var_names, **kwargs)

    def plot(self, kind='trace', **kwargs):
        """Generate various plots of the posterior estimates via ArviZ.

        Args:
            kind (str, optional): The type of ArviZ plot to generate. Can be
                any named function of the form "plot_{}" in the ArviZ
                namespace (e.g., 'trace', 'forest', 'posterior', etc.).
                Defaults to 'trace'.
            kwargs: Optional keyword arguments passed onto the corresponding
                ArviZ plotting function (see ArviZ docs for details).

        Returns:
            A matplotlib or bokeh object, depending on plot kind and kwargs.
        """
        name = 'plot_{}'.format(kind)
        plotter = getattr(az, name)
        if plotter is None:
            raise ValueError("ArviZ has no plotting function '{}'.".format(name))
        plotter(self.data, **kwargs)
