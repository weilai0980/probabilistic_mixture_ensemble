#!/usr/bin/python

import numpy as np
from sklearn.neighbors.kde import KernelDensity

from utils_training import *

class ensemble_inference(object):

    def __init__(self):
        '''
        [A B S]
        A: number of samples
        '''
        self.py_mean_src_samples = []
        self.py_var_src_samples = []
        self.py_gate_src_samples = []
        
        self.py_mean_samples = []
        self.py_var_samples = []
        
        self.py_lk_samples = []
        
    def add_samples(self, 
                    py_mean, 
                    py_var,
                    py_mean_src,
                    py_var_src, 
                    py_gate_src, 
                    py_lk):
        # [A B S]         
        self.py_mean_src_samples.append(py_mean_src)
        self.py_var_src_samples.append(py_var_src)
        self.py_gate_src_samples.append(py_gate_src)
        # [A B 1]
        self.py_mean_samples.append(py_mean)
        self.py_var_samples.append(py_var)
        # [A B]
        self.py_lk_samples.append(py_lk)
        
        return
    
    def softmax_stable(self, 
                       X, 
                       theta = 1.0, 
                       axis = None):
        '''
        logsumexp trick
        
        Compute the softmax of each element along an axis of X.

        Argu.:
          X: ND-Array. Probably should be floats.
          theta (optional): float parameter, used as a multiplier
                          prior to exponentiation. Default = 1.0
          axis (optional): axis to compute values along. Default is the
                         first non-singleton axis.

        Returns an array the same size as X. The result will sum to 1
        along the specified axis.
        '''
        # make X at least 2d
        y = np.atleast_2d(X)

        # find axis
        if axis is None:
            axis = next(j[0] for j in enumerate(y.shape) if j[1] > 1)

        # multiply y against the theta parameter,
        y = y * float(theta)

        # subtract the max for numerical stability
        y = y - np.expand_dims(np.max(y, axis = axis), axis)

        # exponentiate y
        y = np.exp(y)

        # take the sum along the specified axis
        ax_sum = np.expand_dims(np.sum(y, axis = axis), axis)

        # finally: divide elementwise
        p = y / ax_sum

        # flatten if X was 1D
        if len(X.shape) == 1: 
            p = p.flatten()
        
        return p
    
#     def importance_inference(self,
#                              snapshot_features,
#                              y):
#         '''
#         snapshot_features: [A M]
#                             M: feature dimensionality
#         y: [B 1]
#         '''
#         num_snapshot = len(snapshot_features)
#         snapshot_features = np.reshape(np.asarray(snapshot_features), (num_snapshot, -1))
        
#         kde = KernelDensity(kernel = 'gaussian', bandwidth = 0.2).fit(snapshot_features)
#         kde_score = kde.score_samples(snapshot_features)
#         snapshot_imp = self.softmax_stable(kde_score, 
#                                            theta = 1.0, 
#                                            axis = None)
#         snapshot_imp = np.expand_dims(np.asarray(snapshot_imp), axis = 1)
#         print("\n\n ----- test \n", snapshot_imp)
        
#         # [A B S]
#         # A: number of samples
#         m_src_sample = np.asarray(self.py_mean_src_samples)
#         v_src_sample = np.asarray(self.py_var_src_samples)
#         g_src_sample = np.asarray(self.py_gate_src_samples)
#         # [A B 1]
#         m_sample = np.asarray(self.py_mean_samples)
        
#         # -- mean
#         # [B]
#         bayes_mean = np.sum(snapshot_imp*np.sum(m_src_sample*g_src_sample, axis = 2), axis = 0)
        
#         # -- total variance
#         # [B]
#         sq_mean = bayes_mean**2
#         # [A B S]
#         var_plus_sq_mean_src = v_src_sample + m_src_sample**2
#         # [B]
#         bayes_total_var = np.sum(snapshot_imp*np.sum(g_src_sample*var_plus_sq_mean_src, -1), 0) - sq_mean
        
#         # -- volatility
#         # heteroskedasticity
#         # [B]                       [A B S]
#         bayes_vola = np.sum(snapshot_imp*np.sum(g_src_sample*v_src_sample, -1), 0)
        
#         # -- uncertainty on predicted mean
#         # without heteroskedasticity
#         # [B]                       [A B S]
#         bayes_unc = np.sum(snapshot_imp*np.sum(g_src_sample*(m_src_sample**2), -1), 0) - sq_mean
        
#         # -- nnllk
#         # normalized negative log-likelihood
#         # [1 B 1]
#         aug_y = np.expand_dims(y, axis=0)
        
#         # [A B S]
#         tmp_lk_src = np.exp(-0.5*(aug_y - m_src_sample)**2/(v_src_sample + 1e-5))/(np.sqrt(2.0*np.pi*v_src_sample) + 1e-5)
#         # [B]                   [A B S]
#         tmp_lk = np.sum(snapshot_imp*np.sum(g_src_sample*tmp_lk_src, -1), 0)
        
#         nnllk = np.mean(-1.0*np.log(tmp_lk + 1e-5))
        
#         # -- uniform nnllk
#         # take the mixture mean and variance to parameterize one Gaussian distribution
        
#         # [B]
#         uni_nnllk_vol = np.mean(0.5*np.square(np.squeeze(y) - bayes_mean)/(bayes_vola + 1e-5) + 0.5*np.log(bayes_vola + 1e-5) + 0.5*np.log(2*np.pi))

#         uni_nnllk_var = np.mean(0.5*np.square(np.squeeze(y) - bayes_mean)/(bayes_total_var + 1e-5) + 0.5*np.log(bayes_total_var + 1e-5) + 0.5*np.log(2*np.pi))
        
#         # -- gate
#         # [B S]                 [A B S]
#         bayes_gate_src = np.mean(g_src_sample, axis = 0)
#         bayes_gate_src_var = np.var(g_src_sample, axis = 0)
        
#         # -- output
#         tmpy = np.squeeze(y)
        
#         # error tuple [], prediction tuple []
#         return [func_rmse(tmpy, bayes_mean), 
#                 func_mae(tmpy, bayes_mean), 
#                 func_mape(tmpy, bayes_mean), 
#                 func_pearson(tmpy, bayes_mean), 
#                 nnllk, 
#                 uni_nnllk_vol, 
#                 uni_nnllk_var],\
#                [bayes_mean, 
#                 bayes_total_var,
#                 bayes_vola, 
#                 bayes_unc, 
#                 bayes_gate_src, 
#                 bayes_gate_src_var, 
#                 g_src_sample]
        
    def bayesian_inference(self, 
                           y):
        '''
        y: [B 1]
        A: number of samples
        '''
        # [A B S]
        m_src_sample = np.asarray(self.py_mean_src_samples)
        v_src_sample = np.asarray(self.py_var_src_samples)
        g_src_sample = np.asarray(self.py_gate_src_samples)
        # [A B 1]
        m_sample = np.asarray(self.py_mean_samples)
        v_sample = np.asarray(self.py_var_samples)
        # [A B]
        lk_sample = np.asarray(self.py_lk_samples)
        
        # -- mean
        # [B]
        #bayes_mean = np.mean(np.sum(m_src_sample*g_src_sample, axis = 2), axis = 0)
        bayes_mean = np.mean(np.squeeze(m_sample, -1), axis = 0)
        
        # -- total variance
        # [B]
        sq_mean = bayes_mean**2
        # [A B 1]
        var_plus_sq_mean = np.squeeze(v_sample + m_sample**2, -1)
        # [B]
        bayes_var_total = np.mean(var_plus_sq_mean, 0) - sq_mean
        
        # -- data variance
        # heteroskedasticity
        # [B]
        bayes_var_data = np.mean(np.squeeze(v_sample, -1), 0)
        
        # -- model variance
        # [B]                       [A B 1]
        bayes_var_model = np.mean(np.squeeze(m_sample**2, -1), 0) - sq_mean
        
        # -- nnllk
        nnllk = np.mean(-1.0*np.log(np.mean(lk_sample, 0) + 1e-5))
        
        # -- gate
        # [B S]                 [A B S]
        bayes_gate_src = np.mean(g_src_sample, axis = 0)
        bayes_gate_src_var = np.var(g_src_sample, axis = 0)
        
        # -- mean of total variance
        std_total_mean = np.mean(np.sqrt(bayes_var_total))
        
        '''
        # -- total variance
        # [B]
        sq_mean = bayes_mean**2
        # [A B S]
        var_plus_sq_mean_src = v_src_sample + m_src_sample**2
        # [B]
        bayes_var_total = np.mean(np.sum(g_src_sample*var_plus_sq_mean_src, -1), 0) - sq_mean
        
        # -- data variance
        # heteroskedasticity
        # [B]                       [A B S]
        bayes_var_data = np.mean(np.sum(g_src_sample*v_src_sample, -1), 0)
        
        # -- model variance
        # without heteroskedasticity
        # [B]                       [A B S]
        bayes_var_model = np.mean(np.sum(g_src_sample*(m_src_sample**2), -1), 0) - sq_mean
        '''
        
        '''
        # -- nnllk
        # normalized negative log-likelihood
        # [1 B 1]
        aug_y = np.expand_dims(y, axis=0)
        # [A B S]
        tmp_lk_src = np.exp(-0.5*(aug_y - m_src_sample)**2/(v_src_sample + 1e-5))/(np.sqrt(2.0*np.pi*v_src_sample) + 1e-5)
        # [B]                   [A B S]
        tmp_lk = np.mean(np.sum(g_src_sample*tmp_lk_src, -1), 0)
        # normalized                                                                                         
        nnllk = np.mean(-1.0*np.log(tmp_lk + 1e-5))
        '''
        
        '''
        # -- gate uncertainty 
        # infer by truncated Gaussian [0.0, 1.0]
        
        print("-----------------  begin to infer gate uncertainty...\n")
        
        # [B S]
        loc_ini = np.mean(g_src_sample, axis = 0) 
        scale_ini = np.std(g_src_sample, axis = 0)
        
        real_left = 0.0
        real_right = 1.0
        
        # [B S]
        left_ini = 1.0*(real_left - loc_ini)/(scale_ini + 1e-5)
        right_ini = 1.0*(real_right - loc_ini)/(scale_ini + 1e-5)
        
        # [A B S]
        norm_g_src_sample = 1.0*(g_src_sample - loc_ini)/(scale_ini + 1e-5)
        
        def func(p, r, xa, xb):
            return truncnorm.nnlf(p, r)
        
        def constraint(p, r, xa, xb):
            a, b, loc, scale = p
            return np.array([a*scale + loc - xa, b*scale + loc - xb])
        
        # [B S A]       
        batch_src_sample = np.transpose(norm_g_src_sample, [1, 2, 0])
        
        num_batch = np.shape(batch_src_sample)[0]
        num_src = np.shape(batch_src_sample)[1]
        
        # [B S 2]: [B S 0] mean, [B S 1] var
        tr_gau_batch_src = []
        
        for tmp_ins in range(num_batch):
            
            tr_gau_batch_src.append([])
            
            for tmp_src in range(num_src):
                
                tmp_para = fmin_slsqp(func, 
                                      [left_ini[tmp_ins][tmp_src], right_ini[tmp_ins][tmp_src], loc_ini[tmp_ins][tmp_src], scale_ini[tmp_ins][tmp_src]], 
                                      f_eqcons = constraint, 
                                      args = (batch_src_sample[tmp_ins][tmp_src], real_left, real_right),
                                      iprint = False, 
                                      iter = 1000)
                
                tr_gau_batch_src[-1].append([tmp_para[2], tmp_para[3]])
        '''
        # -- output
        
        # error tuple [], prediction tuple []
        y_low_model = bayes_mean - 2.0*np.sqrt(bayes_var_model)
        y_up_model = bayes_mean + 2.0*np.sqrt(bayes_var_model)
        
        y_low_total = bayes_mean - 2.0*np.sqrt(bayes_var_total)
        y_up_total  = bayes_mean + 2.0*np.sqrt(bayes_var_total)
        
#         func_pearson(np.squeeze(y), bayes_mean),
        
        return [func_rmse(np.squeeze(y), bayes_mean),
                func_mae(np.squeeze(y), bayes_mean),
                func_mape(np.squeeze(y), bayes_mean),
                nnllk,
                func_pred_interval_coverage_prob(np.squeeze(y), yhat_low = y_low_model, yhat_up = y_up_model),
                func_pred_interval_coverage_prob(np.squeeze(y), yhat_low = y_low_total, yhat_up = y_up_total),
                func_pred_interval_width(np.squeeze(y), yhat_low = y_low_total, yhat_up = y_up_total), 
                std_total_mean],\
               [bayes_mean,
                bayes_var_total,
                bayes_var_data,
                bayes_var_model,
                bayes_gate_src,
                bayes_gate_src_var,
                g_src_sample]
        
#         return [func_rmse(exp_y, exp_mean),
#                 func_mae(exp_y, exp_mean),
#                 func_mape(exp_y, exp_mean),
#                 func_nnllk_lognormal(nnllk, tmpy),
#                 func_pearson(exp_y, exp_mean),
#                 func_pred_interval_coverage_prob(tmpy, yhat_low = y_low_unc,   yhat_up = y_up_unc),
#                 func_pred_interval_coverage_prob(tmpy, yhat_low = y_low_total, yhat_up = y_up_total),
#                 func_pred_interval_width(tmpy, yhat_low = y_low_total, yhat_up = y_up_total), 
#                 std_mean],\
#                [bayes_mean,
#                 bayes_total_var,
#                 bayes_vola,
#                 bayes_unc,
#                 bayes_gate_src,
#                 bayes_gate_src_var,
#                 g_src_sample]
    
def global_top_steps_multi_retrain(retrain_step_error,
                                   num_step):
        '''
        Argu.:
          retrain_step_error: [[step_error_pairs, retrain_id]]
        '''
        retrain_id_step_error = []
        
        for tmp in retrain_step_error:
            
            tmp_step_errors = tmp[0]
            tmp_retrain_id = tmp[1]
            
            for tmp_step_error in tmp_step_errors:
                #                        id             step               error
                retrain_id_step_error.append([tmp_retrain_id, tmp_step_error[0], tmp_step_error[1]])
                
        sorted_id_step_error = sorted(retrain_id_step_error, key = lambda x:x[-1])
        top_id_step_error = sorted_id_step_error[:num_step]
        
        id_steps = {}
        for i in top_id_step_error:
            tmp_retrain_id = i[0]
            tmp_step = i[1]
            tmp_error = i[2]
            
            if tmp_retrain_id not in id_steps:
                id_steps[tmp_retrain_id] = []
                
            id_steps[tmp_retrain_id].append(tmp_step)
                
        retrain_ids = [tmp_id for tmp_id in id_steps]
        retrain_id_steps = [id_steps[tmp_id] for tmp_id in id_steps]
        
        return retrain_ids, retrain_id_steps
    