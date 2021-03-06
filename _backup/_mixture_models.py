#!/usr/bin/python

import numpy as np
from scipy.stats import truncnorm
from scipy.optimize import fmin_slsqp

import tensorflow as tf
import tensorflow_probability as tfp

from sklearn.neighbors.kde import KernelDensity

# local packages
from utils_libs import *
from utils_linear_units import *
from utils_rnn_units import *
from utils_training import *
from utils_optimization import *

# reproducibility by fixing the random seed
#np.random.seed(1)
#tf.set_random_seed(1)

# ----- Mixture statistic -----

class mixture_statistic():
    
    def __init__(self, 
                 session, 
                 loss_type,
                 num_src, 
                 hyper_para_dict,
                 model_type):
        '''
        Argu.:
          session: tensorflow session
          loss_type: string, type of loss functions, {mse, lk, lk_inv, elbo, ...}
          num_src:
          hyper_para_dict:
          model_type:
        '''
        self.sess = session
        self.loss_type = loss_type
        self.num_src = num_src # number of sources in X
        self.hyper_para_dict = hyper_para_dict
        self.model_type = model_type
        
        self.log_step_error = []
        self.log_error_up_flag = False
        self.stored_step_id = []
        
    def network_ini(self,
                    hyper_para_dict,
                    x_dim,
                    x_steps,
                    x_bool_common_factor,
                    model_type,
                    model_distr_type,
                    model_distr_para,
                    model_var_type,
                    model_para_share_type,
                    bool_regu_mean,
                    bool_regu_var,
                    bool_regu_gate,
                    bool_regu_positive_mean,
                    bool_regu_global_gate,
                    bool_regu_latent_dependence,
                    bool_regu_l2_on_latent,
                    bool_regu_imbalance,
                    latent_dependence,
                    latent_prob_type,
                    bool_bias_mean,
                    bool_bias_var,
                    bool_bias_gate,
                    bool_bias_global_src,
                    optimization_method,
                    optimization_lr_decay,
                    optimization_lr_decay_steps,
                    optimization_burn_in_step,
                    optimization_warmup_step):
        '''
        Argu.:
        
        hyper_para_dict:
        
           lr: float, learning rate
           l2: float, l2 regularization
           batch_size: int
           
           lstm_size: int
           dense_num: int
           use_hidden_before_dense: bool
        
        x_dim:  dimension values for each component in X
        
        x_steps: sequence length values for each component in X
                
        model_distr_type: string, type of the distribution of the target variable
        
        model_distr_para: set of parameters of the associated distribution
        
                    "gaussian": []
                    "student_t": [nu] >= 3
                    
        model_var_type: square or exponential
        
        bool_regu_positive_mean: if regularization of positive mean 
        
        bool_regu_gate: if regularization the gate functions
        
        bool_regu_global_gate: if global gate regularization is applied
        
        latent_dependence: string, dependence of latent logits, "none", "independent", "markov"
        
        latent_prob_type: string, probability calculation of latent logits, "none", "scalar", "vector", "matrix"
        
        bool_bias_mean: have bias in mean prediction
        
        bool_bias_var: have bias in variance prediction
        
        bool_bias_gate: have bias in gate prediction
        
        Dictionary of abbreviation:
        
           nllk: negative log likelihood
           hetero: heteroskedasticity
           inv: inversed
           const: constant
           indi: individual
           py: predicted y
           src: source
           var: variance
         
           A: number of samples
           S: source 
           B: batch size
           T: time steps
           D: data dimensionality at each time step
        '''
        
        # ----- fix the random seed to reproduce the results
        #np.random.seed(1)
        #tf.set_random_seed(1)
        
        # ----- ini 
        self.hyper_para_dict = hyper_para_dict
        
        # build the network graph 
        self.lr = self.hyper_para_dict["lr"]
        
        self.l2_mean = self.hyper_para_dict["l2_mean"]
        self.l2_var = self.hyper_para_dict["l2_var"]
        
        #self.l2 = self.hyper_para_dict["l2"]
        #self.l2 = []
        #for i in range(self.num_src):
        #    self.l2.append(self.hyper_para_dict["l2" + "_" + str(i)])
        
        self.distr_type = model_distr_type
        
        # initialize placeholders
        # y: [B 1]
        self.y = tf.placeholder(tf.float32, 
                                [None, 1], 
                                name = 'y')
        # x: [S, [B T D]]
        self.x = []
        for i in range(self.num_src):
            self.x.append(tf.placeholder(tf.float32, 
                                         [None, x_steps[i], x_dim[i]], 
                                         name = 'x' + str(i)))
        if model_type == "rnn":
            self.keep_prob = tf.placeholder(tf.float32, 
                                            shape = (), 
                                            name = 'keep_prob')
        # -- hyper-parameters
        
        self.bool_regu_l2_on_latent = bool_regu_l2_on_latent
        self.bool_regu_imbalance = bool_regu_imbalance
        
        self.optimization_method = optimization_method
        self.optimization_lr_decay = optimization_lr_decay
        self.optimization_lr_decay_steps = optimization_lr_decay_steps 
        self.optimization_warmup_step = optimization_warmup_step
        
        self.bool_regu_mean = bool_regu_mean
        self.bool_regu_var = bool_regu_var
        
        self.training_step = 0
        
        # ----- individual models
        
        if latent_dependence != "none" :
            
            # x: [S, [B T D]]
            self.pre_x = []
            self.cur_x = []
            for i in range(self.num_src):
                self.pre_x.append(tf.slice(self.x[i], [0, 0, 0], [-1, x_steps[i]-1, -1]))
                self.cur_x.append(tf.slice(self.x[i], [0, 1, 0], [-1, x_steps[i]-1, -1]))
            
            '''
            # [S B T-1 D]
            pre_x = tf.slice(self.x, [0, 0, 0, 0], [-1, -1, x_steps - 1, -1])
            # [S B T-1 D]
            curr_x = tf.slice(self.x, [0, 0, 1, 0], [-1, -1, x_steps - 1, -1])
            
            if model_type == "linear":
                #[S B]
                tmp_mean, regu_mean, tmp_var, regu_var, tmp_curr_logit, regu_gate = \
                multi_src_predictor_linear(x = curr_x, 
                                           n_src = self.num_src, 
                                           steps = x_steps - 1, 
                                           dim = x_dim, 
                                           bool_bias = [bool_bias_mean, bool_bias_var, bool_bias_gate], 
                                           bool_scope_reuse= [False, False, False], 
                                           str_scope = "",
                                           para_share_logit = model_para_share_type)
                #[S B]
                _, _, _, _, tmp_pre_logit, _ = \
                multi_src_predictor_linear(x = pre_x, 
                                           n_src = self.num_src, 
                                           steps = x_steps - 1, 
                                           dim = x_dim, 
                                           bool_bias = [bool_bias_mean, bool_bias_var, bool_bias_gate], 
                                           bool_scope_reuse= [True, True, True], 
                                           str_scope = "",
                                           para_share_logit = model_para_share_type)
            elif model_type == "rnn":
                a = 1
            '''
            placeholder_var = 1
            
        else:
            
            if model_type == "linear":
                #[S B]
                tmp_mean, regu_mean, tmp_var, regu_var, tmp_logit, regu_gate = multi_src_predictor_linear(x = self.x, 
                                                                                                          n_src = self.num_src, 
                                                                                                          steps = x_steps, 
                                                                                                          dim = x_dim, 
                                                                                                          bool_bias = [bool_bias_mean, bool_bias_var, bool_bias_gate], 
                                                                                                          bool_scope_reuse= [False, False, False], 
                                                                                                          str_scope = "linear", 
                                                                                                          para_share_logit = model_para_share_type, 
                                                                                                          bool_common_factor = x_bool_common_factor,
                                                                                                          common_factor_dim = int(self.hyper_para_dict['factor_size']))
            elif model_type == "rnn":
                #[S B]
                tmp_mean, regu_mean, tmp_var, regu_var, tmp_logit, regu_gate = multi_src_predictor_rnn(x = self.x,
                                                                                                       n_src = self.num_src,
                                                                                                       bool_bias = [bool_bias_mean, bool_bias_var, bool_bias_gate],
                                                                                                       bool_scope_reuse = [False, False, False],
                                                                                                       str_scope = "rnn",
                                                                                                       rnn_size_layers = [int(self.hyper_para_dict['rnn_size'])],
                                                                                                       rnn_cell_type = "lstm",
                                                                                                       dropout_keep = self.keep_prob,
                                                                                                       dense_num = int(self.hyper_para_dict['dense_num']),
                                                                                                       max_norm_cons = self.hyper_para_dict['max_norm_cons'])
        # ----- individual means and variance
        
        # -- mean
        if bool_bias_global_src == True:
            
            # global bias term
            global_b = tf.get_variable('global_b',
                                       shape = [1, ],
                                       initializer = tf.zeros_initializer())
            #[1 B]                    [S B]
            tmp_target_src = tf.slice(tmp_mean, [0, 0], [1, -1]) 
            #[S-1 B]
            tmp_rest_src = tf.slice(tmp_mean, [1, 0], [-1, -1])
        
            tmp_target_src = tmp_target_src + global_b
            # [B S]            [S B]
            mean_stack = tf.transpose(tf.concat([tmp_target_src, tmp_rest_src], axis = 0), [1, 0])
        
        else:
            # [B S]
            mean_stack = tf.transpose(tmp_mean, [1, 0])
        
        # -- variance
        if model_var_type == "square":
            # square
            var_stack = tf.transpose(tf.square(tmp_var), [1, 0])
            inv_var_stack = tf.transpose(tf.square(tmp_var), [1, 0])
        elif model_var_type == "exp":
            # exp
            var_stack = tf.transpose(tf.exp(tmp_var), [1, 0])
            inv_var_stack = tf.transpose(tf.exp(tmp_var), [1, 0])
            
        # ----- gates
        
        regu_latent_dependence = 0.0
        
        # -- latent logits dependence
        
        if latent_dependence == "markov":
            
            # [B S]
            pre_logit = tf.transpose(tmp_pre_logit, [1, 0])
            curr_logit = tf.transpose(tmp_curr_logit, [1, 0])
            
            if latent_prob_type == "constant_diff_sq":
            
                # [B 1]
                latent_prob_logits = tf.reduce_sum(tf.square(curr_logit - pre_logit), 1, keep_dims = True)
                
                # regularization
                regu_latent_dependence = 0.0
                
            elif latent_prob_type == "scalar_diff_sq":
                
                # [1]
                w_logit = tf.get_variable('w_logit',
                                          [],
                                          initializer = tf.contrib.layers.xavier_initializer())
                # [B 1]
                latent_prob_logits = w_logit*tf.reduce_sum(tf.square(curr_logit - pre_logit), 1, keep_dims = True)
            
                # regularization
                regu_latent_dependence = tf.square(w_logit)
                
            elif latent_prob_type == "vector_diff_sq":
                
                # [1]
                w_logit = tf.get_variable('w_logit',
                                          [self.num_src, 1],
                                          initializer = tf.contrib.layers.xavier_initializer())
            
                latent_prob_logits = tf.matmul(tf.square(curr_logit - pre_logit), w_logit)
                
                # regularization
                regu_latent_dependence = tf.reduce_sum(tf.square(w_logit))
            
            elif latent_prob_type == "pos_neg_diff_sq":
                
                # [1]
                w_pos = tf.get_variable('w_pos',
                                        [],
                                        initializer = tf.contrib.layers.xavier_initializer())
                
                w_neg = tf.get_variable('w_neg',
                                        [],
                                        initializer = tf.contrib.layers.xavier_initializer())
                # [B 1]
                pos_logits = 1.0*tf.square(w_pos)*tf.reduce_sum(tf.square(curr_logit - pre_logit), 1, keep_dims = True)
                # [B 1]
                neg_logits = -1.0*tf.square(w_neg)*tf.reduce_sum(tf.square(curr_logit - pre_logit), 1, keep_dims = True)
                
                # [B 1]
                latent_prob = 0.5*tf.sigmoid(pos_logits) + 0.5*tf.sigmoid(neg_logits)
                
                # regularization
                regu_latent_dependence = tf.square(w_pos) + tf.square(w_neg)
                
        # -- latent logits 
        
        if latent_dependence == "independent" or latent_dependence == "markov":
            
            # [B S]
            pre_logit = tf.transpose(tmp_pre_logit, [1, 0])
            curr_logit = tf.transpose(tmp_curr_logit, [1, 0])
            
            # [B S]
            gate_logits = curr_logit
        
        elif latent_dependence == "none":
            
            # [B S]
            gate_logits = tf.transpose(tmp_logit, [1, 0])
        
        # obtain the gate values
        self.gates = tf.nn.softmax(gate_logits, axis = -1)
        
        # ----- mixture mean, variance and nllk  
        
        if model_distr_type == 'gaussian':
            
            # -- mean
            # component mean
            # [B S] 
            self.py_mean_src = mean_stack
            # mixture mean
            # [B 1]                      [B S]        [B S]
            self.py_mean = tf.reduce_sum(mean_stack * self.gates, 1, keepdims = True)
            
            # -- variance
            if self.loss_type == 'heter_lk':
                
                # component variance
                self.py_var_src = var_stack
                
                # variance
                sq_mean_stack = var_stack + tf.square(mean_stack)
                # [B 1]                                 [B S]          [B S]
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), 1, keepdims = True)
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
                
                # negative log likelihood
                # [B S]
                lk_src = tf.exp(-0.5*tf.square(self.y-mean_stack)/(var_stack+1e-5))/(tf.sqrt(2.0*np.pi*var_stack)+1e-5)
                                                                                                 
                lk = tf.multiply(lk_src, self.gates) 
                self.nllk = tf.reduce_sum(-1.0*tf.log(tf.reduce_sum(lk, axis = -1) + 1e-5))
                
                self.nllk_bound = self.nllk
                
            elif self.loss_type == 'heter_lk_inv':
                
                # component variance
                self.py_var_src = 1.0/(inv_var_stack + 1e-5)
                
                # variance
                sq_mean_stack = 1.0/(inv_var_stack + 1e-5) + tf.square(mean_stack)
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), 1, keepdims = True)
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
                
                # negative log likelihood
                # [B S]
                lk_src = tf.exp(-0.5*tf.square(self.y - mean_stack)*inv_var_stack)*tf.sqrt(0.5/np.pi*inv_var_stack)
            
                lk = tf.multiply(lk_src, self.gates) 
                self.nllk = tf.reduce_sum(-1.0*tf.log(tf.reduce_sum(lk, axis = -1) + 1e-5))
                
                self.nllk_bound = self.nllk
                
            elif self.loss_type == 'homo_lk_inv':
                
                # variance as trainable parameter
                # [1 S]
                inv_var_homo = tf.get_variable('homo_var_src', 
                                               [1, self.num_src],
                                               initializer = tf.contrib.layers.xavier_initializer())
                
                # re-set regularization on variance terms
                regu_var = tf.reduce_sum(inv_var_homo * inv_var_homo)
                
                # component variance
                self.py_var_src = 1.0/(inv_var_homo + 1e-5)
                
                # variance
                sq_mean_stack = 1.0/(inv_var_homo + 1e-5) + tf.square(mean_stack)
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), 1, keepdims = True)
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
                
                # negative log likelihood
                # [B S]
                lk_src = tf.exp(-0.5*tf.square(self.y - mean_stack)*inv_var_homo)*tf.sqrt(0.5/np.pi*inv_var_homo)
            
                lk = tf.multiply(lk_src, self.gates) 
                self.nllk = tf.reduce_sum(-1.0*tf.log(tf.reduce_sum(lk, axis = -1) + 1e-5))
                
                self.nllk_bound = self.nllk
            
            # elbo: evidence lower bound optimization    
            elif self.loss_type == 'heter_elbo':
                
                # component variance
                self.py_var_src = 1.0/(inv_var_stack + 1e-5)
                
                # variance
                sq_mean_stack = 1.0/(inv_var_stack + 1e-5) + tf.square(mean_stack)
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), 1, keepdims = True)
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
                
                # negative log likelihood
                # based on lk_inv
                
                # [B S]
                lk_src = tf.exp(-0.5*tf.square(self.y-mean_stack)*inv_var_stack)*tf.sqrt(0.5/np.pi*inv_var_stack)
            
                lk = tf.multiply(lk_src, self.gates) 
                self.nllk = tf.reduce_sum(-1.0*tf.log(tf.reduce_sum(lk, axis = -1) + 1e-5))
                
                # [B 1] - [B S]
                tmp_nllk_bound = .5*tf.square(self.y - mean_stack)*inv_var_stack - 0.5*tf.log(inv_var_stack + 1e-5) + 0.5*tf.log(2*np.pi)
        
                self.nllk_bound = tf.reduce_sum(tf.reduce_sum(self.gates*tmp_nllk_bound, -1)) 
            
            elif self.loss_type == 'mse':
                
                # component variance
                self.py_var_src = tf.constant(1.0, shape = [1, self.num_src])
                
                # variance
                sq_mean_stack = 1.0 + tf.square(mean_stack)
                # [B 1]
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), 1, keepdims = True)
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
                
                # negative log likelihood
                # [B S]
                # ? variance of constant 1 
                lk_src = tf.exp(-0.5*tf.square(self.y - mean_stack))/(2.0*np.pi)**0.5
            
                lk = tf.multiply(lk_src, self.gates) 
                self.nllk = tf.reduce_sum(-1.0*tf.log(tf.reduce_sum(lk, axis = -1) + 1e-5))
            
            # elif self.loss_type == 'stacking':
            
            ''' 
            elif self.loss_type == 'lk_var_mix':
                
                # mixed variance
                # [B 1]                     [B S]     [B S]
                self.py_var = tf.reduce_sum(var_stack * self.gates, 1, keepdims = True)
                
                # negative log likelihood
                # [B]
                tmp_nllk_var_mix = 0.5*tf.square(self.y - self.py_mean)/(self.py_var + 1e-5) + 0.5*tf.log(self.py_var + 1e-5)\
                           + 0.5*tf.log(2*np.pi)
            
                self.nllk_var_mix = tf.reduce_sum(tmp_nllk_mix) 
            
            elif self.loss_type == 'lk_var_mix_inv':
                
                # mixed variance
                # [B 1]                     [B S]         [B S]
                py_var_inv = tf.reduce_sum(inv_var_stack * self.gates, 1, keepdims = True)
                # [B 1]
                self.py_var = tf.reduce_sum(1.0/(inv_var_stack + 1.0) * self.gates, 1, keepdims = True)
                
                # negative log likelihood
                # [B]
                # self.py_var is inversed
                tmp_nllk_var_mix_inv = 0.5*tf.square(self.y - self.py_mean)*py_var_inv - 0.5*tf.log(py_var_inv + 1e-5)\
                               + 0.5*tf.log(2*np.pi)
            
                self.nllk_var_mix_inv = tf.reduce_sum(tmp_nllk_mix_inv)
            ''' 
         
        '''
        elif model_distr_type == 'student_t':
            
            # for negative log likelihood
            t_distr_constant = 1.0/(np.sqrt(model_distr_para[0])*sp.special.beta(0.5,model_distr_para[0]/2.0)+ 1e-5)
            
            # -- mean
            
            # component mean
            self.py_mean_src = mean_stack
            
            # mixture mean
            # [B 1]                      [B S]       [B S]
            self.py_mean = tf.reduce_sum(mean_stack * self.gates, 1, keepdims = True)
            
            # -- variance
            
            # variance of mixture
            if self.loss_type == 'lk':
                
                # component variance
                # [B S]    
                self.py_var_src = var_stack*1.0*model_distr_para[0]/(model_distr_para[0]-2.0) # "nu"
                
                # variance
                sq_mean_stack = var_stack*1.0*model_distr_para[0]/(model_distr_para[0]-2.0) + tf.square(mean_stack)
                
                # [B 1]                                   [B S]          [B S]
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), 1,  keepdims = True)
                
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
            
                # [B S]
                # self.x: [S B T D]
            
                # [B S]
                normalizer_src = t_distr_constant/(tf.sqrt(var_stack) + 1e-5)
                #1.0/(tf.sqrt(distr_para[0]*var_stack)*sp.special.beta(0.5, distr_para[0]/2.0) + 1e-5)
            
                base_src = 1.0 + 1.0*tf.square(self.y - mean_stack)/model_distr_para[0]/(var_stack + 1e-5)
            
                lk_src = normalizer_src*tf.keras.backend.pow(base_src, -(model_distr_para[0] + 1)/2)
        
                lk = tf.multiply(lk_src, self.gates) 
                self.nllk = tf.reduce_sum(-1.0*tf.log(tf.reduce_sum(lk, axis = -1) + 1e-5))
                
            elif self.loss_type == 'lk_inv' :
                
                # component variance
                # [B S]    
                self.py_var_src = 1.0*model_distr_para[0]/(model_distr_para[0]-2.0)/(inv_var_stack + 1e-5) # "nu"
                
                # variance
                sq_mean_stack = self.py_var_src + tf.square(mean_stack)
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), keepdims = True)
                
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
                
                # negative log likelihood
                # [B S]
                normalizer_src = t_distr_constant*tf.sqrt(inv_var_stack)
            
                base_src = 1.0 + 1.0*tf.square(self.y - mean_stack)/model_distr_para[0]*inv_var_stack
            
                lk_src = normalizer_src*tf.keras.backend.pow(base_src, -(model_distr_para[0] + 1)/2)
            
                lk = tf.multiply(lk_src, self.gates) 
                self.nllk = tf.reduce_sum(-1.0*tf.log(tf.reduce_sum(lk, axis = -1) + 1e-5))
                
                
            elif self.loss_type == 'elbo':
                
                # component variance
                # [B S]    
                self.py_var_src = 1.0*model_distr_para[0]/(model_distr_para[0]-2.0)/(inv_var_stack + 1e-5) # "nu"
                
                sq_mean_stack = self.py_var_src + tf.square(mean_stack)
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), keepdims = True)
                
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
                
            elif self.loss_type == 'mse':
                
                # component variance
                self.py_var_src = 1.0
                
                sq_mean_stack = 1.0 + tf.square(mean_stack)
                # [B 1]
                mix_sq_mean = tf.reduce_sum(tf.multiply(sq_mean_stack, self.gates), 1, keepdims = True)
                
                # [B 1]
                self.py_var = mix_sq_mean - tf.square(self.py_mean)
                
            elif self.loss_type == 'var_mix':
                
                # mixed variance
                # [B 1]                     [B S]     [B S]
                self.py_var = tf.reduce_sum(var_stack * self.gates, 1, keepdims = True)
                
            elif self.loss_type == 'var_mix_inv':
                
                # mixed variance
                # [B 1]                     [B S]         [B S]
                self.py_var = tf.reduce_sum(inv_var_stack * self.gates, 1, keepdims = True)
            '''
        
        # ----- regularization
        # [S]
        self.regu_var = regu_var 
        self.regu_mean = regu_mean         
        
        self.regularization = 0
        
        # -- non-negative hinge regularization 
        if bool_regu_positive_mean == True:
            # regu_mean_pos = tf.reduce_sum(tf.maximum(0.0, -1.0*mean_v) + tf.maximum(0.0, -1.0*mean_x))
            self.regularization += regu_mean_pos
        
        # -- latent dependence parameter
        if bool_regu_latent_dependence == True:
            self.regularization += regu_latent_dependence
        
        # -- weights in gates  
        if bool_regu_gate == True:
            self.regularization += regu_gate
        
        # -- global logits
        # implicitly regularization on weights of gate functions
        if bool_regu_global_gate == True:
            
            # for regularization
            # [1 S]
            self.global_logits = tf.get_variable('global_logits', 
                                                 [1, self.num_src],
                                                 initializer = tf.contrib.layers.xavier_initializer())
            # [B S]        [1 S]
            logits_diff_sq = tf.reduce_sum(tf.square(gate_logits - self.global_logits), 1)
            regu_global_logits = tf.reduce_sum(logits_diff_sq) + tf.nn.l2_loss(self.global_logits)
            
            self.regularization += regu_global_logits
        
        # -- gate smoothing
        if latent_prob_type != "none":
            
            if latent_prob_type == "pos_neg_diff_sq":
                # exact llk
                # self.latent_depend = -1.0*tf.reduce_sum(tf.log(latent_prob))
                
                # lower bound, comparable perforamcne to exact llk 
                self.latent_depend = 0.5*(tf.reduce_sum(tf.log(1.0 + tf.exp(-1.0*pos_logits))))\
                                                                + \
                                     0.5*(tf.reduce_sum(tf.log(1.0 + tf.exp(neg_logits)) - 1.0*neg_logits))
            else:
                # ! numertical stable version of log(sigmoid()) !
                # avoid the overflow of exp(-x) in sigmoid, when -x is positive large 
                # [B 1]
                self.latent_depend = (tf.reduce_sum(tf.log(1.0 + tf.exp(-1.0*tf.abs(latent_prob_logits))) \
                                           + tf.maximum(0.0, -1.0*latent_prob_logits))) 
        else:
            self.latent_depend = 0.0
        
    #   initialize loss and optimization operations for training
    def train_ini(self):
        
        # ----- loss 
        self.monitor = []
        
        # loss
        if self.loss_type == 'mse':
            
            self.loss = tf.reduce_mean(tf.square(self.y - self.py_mean)) + \
                        self.l2*self.regularization + self.l2*self.regu_mean
            self.monitor = [tf.reduce_mean(tf.square(self.y - self.py_mean)), self.l2*self.regu_mean]
            
        # nllk        
        elif self.loss_type in ['heter_lk', 'heter_lk_inv', 'homo_lk_inv']:
            
            self.loss = self.nllk + self.l2*self.regularization 
            self.monitor = [self.nllk]
            
            if self.bool_regu_mean == True:
                self.loss += (self.l2_mean*self.regu_mean)
                self.monitor.append(self.l2_mean*self.regu_mean)
                
            #    tmp_regu_mean = sum([self.l2[i]*self.regu_mean[i] for i in range(self.num_src)])
            #    self.loss += tmp_regu_mean
            #    self.monitor.append(tmp_regu_mean)
                                
            if self.bool_regu_var == True:
                self.loss += (self.l2_var*self.regu_var)
                self.monitor.append(self.l2_var*self.regu_var)
                
                '''
                if self.bool_regu_imbalance == True:
                    self.loss += (100*self.l2*self.regu_var)
                    self.monitor.append(100*self.l2*self.regu_var)
                else:
                    self.loss += (self.l2_var*self.regu_var)
                    self.monitor.append(self.l2_var*self.regu_var)
                '''
                
            #    tmp_regu_var = sum([self.l2[i]*self.regu_var[i] for i in range(self.num_src)])
            #    self.loss += tmp_regu_var
            #    self.monitor.append(tmp_regu_var)
                                
            if self.bool_regu_l2_on_latent == True:
                self.loss += self.l2*self.latent_depend
                #self.monitor.append(self.l2*self.latent_depend)
                
            else:
                self.loss += self.latent_depend
                #self.monitor.append(self.latent_depend)
        '''
        elif self.loss_type == 'elbo':
            
            self.loss = self.nllk_elbo + 0.1*self.l2*self.regularization + self.l2*(self.regu_mean + self.regu_var)
            
            
        elif self.loss_type == 'simple_mix':
            
            # ?
            self.loss = self.nllk_mix + 0.1*self.l2*self.regularization + self.l2*(self.regu_mean + self.regu_var)
                        #self.nllk_gate + \
                        
         
        elif self.loss_type == 'simple_mix_inv':
            
            # ?
            self.loss = self.nllk_mix_inv + 0.1*self.l2*self.regularization + self.l2*(self.regu_mean + self.regu_var)
                        #self.nllk_gate + \
        '''
        
        # ----- learning rate set-up
        tf_learning_rate = tf.constant(value = self.lr, 
                                       shape = [], 
                                       dtype = tf.float32)
        global_step = tf.train.get_or_create_global_step()
        
        # -- decay
        if self.optimization_lr_decay == True:
            decay_learning_rate = tf.train.exponential_decay(tf_learning_rate, 
                                                             global_step,
                                                             decay_steps = self.optimization_lr_decay_steps, 
                                                             decay_rate = 0.96, 
                                                             staircase = True)
        else:
            decay_learning_rate = tf_learning_rate
        
        # -- learning rate warm-up
        # ref: https://github.com/google-research/bert/blob/ffbda2a1aafe530525212d13194cc84d92ed0313/optimization.py#L29-L65
        if self.optimization_warmup_step > 0:
            
            global_steps_int = tf.cast(global_step, 
                                       tf.int32)
            warmup_steps_int = tf.constant(self.optimization_warmup_step, 
                                           dtype = tf.int32)
            
            global_steps_float = tf.cast(global_steps_int, 
                                         tf.float32)
            warmup_steps_float = tf.cast(warmup_steps_int, 
                                         tf.float32)
            
            warmup_percent_done = global_steps_float / warmup_steps_float
            warmup_learning_rate = tf_learning_rate * warmup_percent_done
                
            is_warmup = tf.cast(global_steps_int < warmup_steps_int, 
                                tf.float32)
                
            optimizer_lr = ((1.0 - is_warmup) * decay_learning_rate + is_warmup * warmup_learning_rate)
        
        else:
            optimizer_lr = decay_learning_rate
        
        # ----- optimizer
        
        # -- conventional 
        if self.optimization_method == 'adam':
            train_optimizer = myAdamOptimizer(learning_rate = optimizer_lr)
            
        elif self.optimization_method == 'adam_origin':
            train_optimizer = tf.train.AdamOptimizer(learning_rate = optimizer_lr)
            
        elif self.optimization_method == 'RMSprop':
            train_optimizer = myRMSprop(learning_rate = optimizer_lr)
            
        elif self.optimization_method == 'RMSprop_origin':
            train_optimizer = tf.train.RMSPropOptimizer(learning_rate = optimizer_lr)
            
        elif self.optimization_method == 'sgd':
            train_optimizer = tf.train.MomentumOptimizer(learning_rate = optimizer_lr,
                                                         momentum = 0.9,
                                                         use_nesterov = True)
        elif self.optimization_method == 'adamW':
            # ref.: "Fixing Weight Decay Regularization in Adam", https://arxiv.org/abs/1711.05101
            train_optimizer = tf.contrib.opt.AdamWOptimizer(weight_decay = self.l2,
                                                            learning_rate = optimizer_lr)
        # -- SG-MCMC
        # stochastic gradient Monto-Carlo Markov Chain
        elif self.optimization_method == 'sg_mcmc_adam':
            train_optimizer = sg_mcmc_adam(learning_rate = optimizer_lr)
            
        elif self.optimization_method == 'sg_mcmc_adam_revision':
            train_optimizer = sg_mcmc_adam_revision(learning_rate = optimizer_lr)
            
        elif self.optimization_method == 'sg_mcmc_RMSprop':
            train_optimizer = sg_mcmc_RMSprop(learning_rate = optimizer_lr)
            
        elif self.optimization_method == 'sgld':
            train_optimizer = StochasticGradientLangevinDynamics(learning_rate = optimizer_lr)
            
        else:
            print("\n --- OPTIMIZER ERROR ---- \n")
        
        # -- training operation
        self.train_op = train_optimizer.minimize(self.loss,
                                                 global_step = global_step)
        # -- initialize the graph
        self.init = tf.global_variables_initializer()
        self.sess.run(self.init)
        
    #   training on batch of data
    def train_batch(self, 
                    x, 
                    y,
                    global_step):
        '''
        Argu.:
          global_step: in epoch 
        '''
        data_dict = {}
        data_dict["y:0"] = y
        
        # x: [S, [B T D]]
        for i in range(len(x)):
            data_dict["x" + str(i) + ":0"] = x[i]
        
        if self.model_type == "rnn":
            data_dict["keep_prob:0"] = self.hyper_para_dict['dropout_keep_prob']
            
        # record the global training step 
        self.training_step = global_step
        
        _ = self.sess.run(self.train_op,
                          feed_dict = data_dict)
        return
    
    def inference_ini(self):
        
        # --- error metric
        # RMSE
        self.rmse = tf.sqrt(tf.losses.mean_squared_error(self.y, self.py_mean))
        
        # MAE
        self.mae = tf.reduce_mean(tf.abs(self.y - self.py_mean))
        
        # MAPE
        # based on ground-truth y
        mask = tf.greater(tf.abs(self.y), 1e-5)
        
        y_mask = tf.boolean_mask(self.y, mask)
        y_hat_mask = tf.boolean_mask(self.py_mean, mask)
        
        self.mape = tf.reduce_mean(tf.abs((y_mask - y_hat_mask)/(y_mask + 1e-10)))
        
        # NNLLK 
        # normalized negative log likelihood by the number of data samples
        # x: [S, [B T D]]
        self.nnllk = self.nllk / tf.to_float(tf.shape(self.x[0])[0])
        
        # ---for model restore and inference
        
        # error metric
        tf.add_to_collection("rmse", self.rmse)
        tf.add_to_collection("mae", self.mae)
        tf.add_to_collection("mape", self.mape)
        tf.add_to_collection("nnllk", self.nnllk)
        
        # monitor metric
        for tmp_idx, tmp_monitor_metric in enumerate(self.monitor):
            tf.add_to_collection(str(tmp_idx), tmp_monitor_metric)
        
        # prediction
        tf.add_to_collection("py_mean", self.py_mean)
        tf.add_to_collection("py_var", self.py_var)
        tf.add_to_collection("py_gate", self.gates)
        
        tf.add_to_collection("py_mean_src", self.py_mean_src)
        tf.add_to_collection("py_var_src", self.py_var_src)
        
    # step-wise
    def validation(self,
                   x,
                   y,
                   snapshot_type,
                   snapshot_Bernoulli,
                   step,
                   bool_end_of_epoch):
        '''
        Argu.:
          x: [S [B T D]]
          y: [B 1]
        '''
        if bool_end_of_epoch == True:
        #or (snapshot_type == "batch_wise" and np.random.binomial(1, snapshot_Bernoulli) == 1):
            
            # data preproc
            data_dict = {}
            data_dict["y:0"] = y
            
            for i in range(len(x)):
                data_dict["x" + str(i) + ":0"] = x[i]
                                
            if self.model_type == "rnn":
                data_dict["keep_prob:0"] = 1.0
            
            # errors           
            rmse, mae, mape, nnllk = self.sess.run([tf.get_collection('rmse')[0],
                                                    tf.get_collection('mae')[0],
                                                    tf.get_collection('mape')[0],
                                                    tf.get_collection('nnllk')[0]],
                                                   feed_dict = data_dict)
            # monitor metric
            monitor_metric = self.sess.run([tf.get_collection(str(tmp_idx))[0] for tmp_idx in range(len(self.monitor))],
                                           feed_dict = data_dict)
            
            # validation error log for early stopping
            self.log_step_error.append([self.training_step, [rmse, mae, mape, nnllk]])
            
            # error metric tuple: [rmse, mae, mape, nnllk]
            # monitor tuple: []
            return [rmse, mae, mape, nnllk], monitor_metric
        
        return None, None
        
    # infer given testing data
    def inference(self, 
                  x, 
                  y,
                  bool_py_eval):
        '''
        Argu.:
          x: [S [B T D]]
          y: [B 1]
        '''
        # --
        data_dict = {}
        data_dict['y:0'] = y
        
        for i in range(len(x)):
            data_dict["x" + str(i) + ":0"] = x[i]
            
        if self.model_type == "rnn":
            data_dict["keep_prob:0"] = 1.0
        
        rmse, mae, mape, nnllk = self.sess.run([tf.get_collection('rmse')[0],
                                                tf.get_collection('mae')[0],
                                                tf.get_collection('mape')[0],
                                                tf.get_collection('nnllk')[0]],
                                               feed_dict = data_dict)
        if bool_py_eval == True:
            # [B 1]  [B 1]   [B S]
            py_mean, py_var, py_gate_src, py_mean_src, py_var_src = self.sess.run([tf.get_collection('py_mean')[0],
                                                                                   tf.get_collection('py_var')[0],
                                                                                   tf.get_collection('py_gate')[0],
                                                                                   tf.get_collection('py_mean_src')[0],
                                                                                   tf.get_collection('py_var_src')[0]],
                                                                                  feed_dict = data_dict)
        else:
            py_mean = None
            py_var = None
            py_gate_src = None
            py_mean_src = None
            py_var_src = None
        
        # error metric tuple [rmse, mae, mape, nnllk], py tuple []
        return [rmse, mae, mape, nnllk], [py_mean, py_var, py_mean_src, py_var_src, py_gate_src]
    
    def model_stored_id(self):
        return self.stored_step_id
    
    def model_saver(self, 
                    path,
                    epoch,
                    step,
                    top_snapshots,
                    bayes_snapshots,
                    early_stop_bool,
                    early_stop_window, 
                    tf_saver):
        
        # -- early stopping
        # self.log_step_error: [self.training_step, [rmse, mae, mape, nnllk]]
        '''
        if early_stop_bool == True:
            
            if len(self.stored_step_id) < 5 and self.training_step >= early_stop_window:
                
                tmp_last_error = self.log_step_error[-1][1][0]
                tmp_window_error = np.mean([i[1][0] for i in self.log_step_error[-1*(early_stop_window + 1):-1]])
                
                if tmp_window_error < tmp_last_error:
                    
                    if self.log_error_up_flag == False:
                        self.stored_step_id.append(self.training_step - 1)
                    
                        saver = tf.train.Saver()
                        saver.save(self.sess, path)
                        
                        #  avoid consecutive upward 
                        self.log_error_up_flag = True
                        return True
                else:
                    self.log_error_up_flag = False
        '''
        # -- best snapshots
        if len(top_snapshots) != 0 and epoch in top_snapshots:
            tf_saver.save(self.sess, path)
            return "best_snapshots"
        
        # -- bayesian ensembles
        elif len(bayes_snapshots) != 0 and epoch in bayes_snapshots:            
            tf_saver.save(self.sess, path)
            return "bayeisan_snapshots"
        
        return None
        
    #   restore the model from the files
    def model_restore(self,
                      path_meta, 
                      path_data, 
                      saver):
        saver.restore(self.sess, 
                      path_data)
        return
    '''
    #   collect the optimized variable values
    def collect_coeff_values(self, 
                             vari_keyword):
        
        return [tf_var.name for tf_var in tf.trainable_variables() if (vari_keyword in tf_var.name)],\
               [tf_var.eval() for tf_var in tf.trainable_variables() if (vari_keyword in tf_var.name)]
    '''
