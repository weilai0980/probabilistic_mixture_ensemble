#!/usr/bin/python

import numpy as np
import tensorflow as tf

# local 
from utils_libs import *

# ----- randomness
def fix_randomness(seed):
    np.random.seed(seed)
    tf.set_random_seed(seed)

# ----- data preparation 

def data_reshape(data, 
                 bool_target_seperate):
    '''
    Argu.:
     S: source
     N: instance
     T: time steps
     D: dimensionality at each step
    
     data: [yi, ti, [xi_src1, xi_src2, ...]]
     by default, the first element in the xi_src1 is the auto-regressive target
    '''
    src_num = len(data[0][2])
    tmpx = []
    
    if bool_target_seperate == True:
        
        tmpx.append(np.asarray([tmp[2][0][:, 1:] for tmp in data]))
        print(np.shape(tmpx[-1]))
    
        for src_idx in range(1, src_num):
            tmpx.append(np.asarray([tmp[2][src_idx] for tmp in data]))
            print(np.shape(tmpx[-1]))
            
        tmpx.append(np.asarray([tmp[2][0][:, 0:1] for tmp in data]))
        print(np.shape(tmpx[-1]))
    
    else:
        for src_idx in range(src_num):
            tmpx.append(np.asarray([tmp[2][src_idx] for tmp in data]))
            print("src " + str(src_idx) + " : ", np.shape(tmpx[-1]))
    
    tmpy = np.asarray([tmp[0] for tmp in data])
    
    if len(np.shape(tmpy)) == 1:
        tmpy = np.expand_dims(tmpy, -1)
        
    # output shape: x [S N T D],  y [N M]
    return tmpx, tmpy

def data_padding_x(x, 
                   num_src):
    '''
    Argu.:
     shape of x: [S N T D]
     T and D are different across sources
    '''
    num_samples = len(x[0])
    
    max_dim_t =  max([np.shape(x[i][0])[0] for i in range(num_src)])
    max_dim_d =  max([np.shape(x[i][0])[1] for i in range(num_src)])
    
    target_shape = [num_samples, max_dim_t, max_dim_d]
    
    target_x = []
    
    for tmp_src in range(num_src):
        
        zero_mask = np.zeros(target_shape)
        
        tmp_t = np.shape(x[tmp_src][0])[0]
        tmp_d = np.shape(x[tmp_src][0])[1]
        # ?? front or end ??
        zero_mask[:, :tmp_t, :tmp_d] = x[tmp_src]
        
        target_x.append(zero_mask)
    
    # [S N T D]
    return target_x

# ----- error metrics

def func_rmse(y,
              yhat):
    return np.sqrt(np.mean( (np.asarray(y) - np.asarray(yhat))**2) )

def func_mae(y, 
             yhat):
    return np.mean(np.abs(np.asarray(y) - np.asarray(yhat)))

def func_mape(y, 
              yhat):
    tmp_list = []
    
    for idx, val in enumerate(y):
        if abs(val) > 1e-5:
            tmp_list.append(abs(1.0*(yhat[idx]-val)/val))
    
    return np.mean(tmp_list)

def func_pearson(y, 
                 yhat):
    import scipy as sp
    return sp.stats.pearsonr(y, yhat)

def func_pred_interval_coverage_prob(y,
                                     yhat_low,
                                     yhat_up):
    in_cnt = 0
    for i in range(len(y)):
        if yhat_low[i] <= y[i] and y[i] <= yhat_up[i]:
            in_cnt += 1
    return 1.0*in_cnt/len(y)

def func_pred_interval_width(y,
                             yhat_low,
                             yhat_up):
    in_cnt = 0
    in_width_sum = 0.0
    for i in range(len(y)):
        if yhat_low[i] <= y[i] and y[i] <= yhat_up[i]:
            in_cnt += 1
            in_width_sum += (yhat_up[i]-yhat_low[i])
            
    return 1.0*in_width_sum/in_cnt

# def func_nnllk_lognormal(nnllk, y):
#     return np.mean(y) + nnllk
    
# ----- logging

def log_train_val_performance(path, 
                              hpara, 
                              hpara_error, 
                              train_time):
    with open(path, "a") as text_env:
        text_env.write("%s, %s, %s\n"%(str(hpara), str(hpara_error), str(train_time)))
        
def log_val_hyper_para(path, 
                       hpara_tuple, 
                       error_tuple, 
                       log_string):
    with open(path, "a") as text_file:
        text_file.write("\n" + log_string + " hyper-parameters: %s \n"%(str(hpara_tuple)))
        text_file.write("\n   validation performance: %s \n"%(str(error_tuple)))
        
def log_test_performance(path, 
                         error_tuple,
                         ensemble_str):
    with open(path, "a") as text_file:
        text_file.write("\n  %s : %s \n"%(ensemble_str, str(error_tuple)))
        
def log_null_loss_exception(epoch_errors, 
                            log_path):
    '''
    Argu.:
      epoch_errors: [ [step, tr_metric, val_metric, epoch] ]    
    '''
    for i in epoch_errors:
        if np.isnan(i[1][0]) == True:
            with open(log_path, "a") as text_file:
                text_file.write("\n  NULL loss exception at: %s \n"%(str(i[0])))
            break
    return

# ----- hyper-parameter searching 

def training_para_gen(shape_x_dict, 
                      hpara_dict):
    tr_dict = {}
    
    ''' ? np.ceil ? '''
    tr_dict["batch_per_epoch"] = int(np.ceil(1.0*shape_x_dict["N"]/int(hpara_dict["batch_size"])))
    tr_dict["tr_idx"] = list(range(shape_x_dict["N"]))
    tr_dict["tr_num_ins"] = shape_x_dict["N"]
    
    return tr_dict

# hpara: hyper-parameter    
class hyper_para_grid_search(object):
    
    def __init__(self, 
                 hpara_range):
        
        # lr_range, batch_size_range, l2_range
        self.n_hpara = len(hpara_range)
        self.hpara_range = hpara_range
        self.ini_flag = True
        self.idx = [0 for _ in range(self.n_hpara)]
        
    def one_trial(self):
        
        if self.ini_flag == True or self.trial_search(self.idx, 0, False) == True:
            self.ini_flag = False
            return [self.hpara_range[i][self.idx[i]] for i in range(self.n_hpara)]
        else:
            return None
        
    def trial_search(self, 
                     idx, 
                     cur_n, 
                     bool_restart):
        
        if cur_n >= self.n_hpara:
            return False
        
        if bool_restart == True:
            self.idx[cur_n] = 0
            self.trial_search(idx, cur_n + 1, True)
            return True
        else:
            if self.trial_search(self.idx, cur_n + 1, False) == False:
                if self.idx[cur_n] + 1 < len(self.hpara_range[cur_n]):
                    
                    self.idx[cur_n] += 1
                    self.trial_search(self.idx, cur_n + 1, True)
                    return True
                
                else:
                    return False
            else:
                return True
            
class hyper_para_random_search(object):
    
    def __init__(self, 
                 hpara_range_dict, 
                 n_trial):
        '''
        Argu.:
          hpara_range_dict: [[lower_boud, up_bound]]
        '''
        # fix local random seed
        np.random.seed(100)
        
        self.n_trial = n_trial
        self.cur_trial = 0
        
        self.hpara_names = []
        self.hpara_range = []
        for tmp_name in hpara_range_dict:
            self.hpara_range.append(hpara_range_dict[tmp_name])
            self.hpara_names.append(tmp_name)
            
        self.n_hpara = len(self.hpara_range)
        
        # no duplication
        self.hpara_set = set()
        self.ini_flag = True
        
    def one_trial(self):
        
        if self.cur_trial < self.n_trial:
            self.cur_trial += 1
            return self.trial_search()
        else:
            return None
        
    def trial_search(self):
        '''
        Return:
          a name-value hyper-para dictionary
        '''
        bool_duplicate = True
        
        while bool_duplicate == True:
            
            tmp_hpara = ()
            for i in self.hpara_range:
                tmp_hpara = tmp_hpara + (i[0] + (i[1] - i[0])*np.random.random(), )
            
            # -- reconstruct the name-value hyper-para dictionary
            if tmp_hpara not in self.hpara_set:
                
                bool_duplicate = False
                self.hpara_set.add(tmp_hpara)
                
                hpara_instance = {} # {hpara names: values}
                for idx, tmp_hpara_val in enumerate(list(tmp_hpara)):
                    hpara_instance[self.hpara_names[idx]] = tmp_hpara_val
                
                return hpara_instance
        return
        
def hyper_para_selection(hpara_log, 
                         val_snapshot_num, 
                         test_snapshot_num,
                         metric_idx):
    '''
    Argu.:
      hpara_log - [ dict{lr, batch, l2, ..., burn_in_steps}, [[step, tr_metric, val_metric, epoch]] ]
    '''
    hp_err = []
    
    for hp_epoch_err in hpara_log:
        hp_err.append([hp_epoch_err[0], hp_epoch_err[1], np.mean([k[2][metric_idx] for k in hp_epoch_err[1][:val_snapshot_num]])])
    
    # sorted_hp[0]: hyper-para with the best validation performance
    sorted_hp = sorted(hp_err, key = lambda x:x[-1])
    
    # -- bayes steps
    full_steps = [k[0] for k in sorted_hp[0][1]]
    
    tmp_burn_in_step = sorted_hp[0][0]["burn_in_steps"]
    bayes_steps = [i for i in full_steps if i >= tmp_burn_in_step]
    bayes_steps_features = [ [k[2]] for k in sorted_hp[0][1] if k[0] >= tmp_burn_in_step ]
    
    # -- top steps
    snapshot_steps = full_steps[:len(bayes_steps)]
    snapshot_steps_features = [ [k[2]] for k in sorted_hp[0][1][:len(bayes_steps)] ]
    
    best_hyper_para_dict = sorted_hp[0][0]
    # best hyper-para, top_steps, bayes_steps
    return best_hyper_para_dict,\
           snapshot_steps,\
           bayes_steps,\
           snapshot_steps_features,\
           bayes_steps_features

def snapshot_selection(train_log, 
                       snapshot_num,
                       total_step_num, 
                       metric_idx, 
                       val_snapshot_num):
    '''
    Argu.:
      train_log: [[step, tr_metric, val_metric, epoch]] 
    '''
    full_steps = [k[0] for k in train_log]
    
    val_error = np.mean([tmp_step[2][metric_idx] for tmp_step in train_log][:val_snapshot_num])
    
    step_error_pairs = []
    for tmp_record in train_log:
        step_error_pairs.append([tmp_record[0], tmp_record[2][metric_idx]])
        
    # -- bayes steps    
    bayes_steps = [i for i in full_steps if i >= (total_step_num - snapshot_num)]  
    bayes_steps_features = [ [k[2]] for k in train_log if k[0] >= (total_step_num - snapshot_num) ]
    
    # -- top steps
    snapshot_steps = full_steps[:len(bayes_steps)]
    snapshot_steps_features = [ [k[2]] for k in train_log[:len(bayes_steps)] ]
    
    # top_steps, bayes_steps
    return snapshot_steps,\
           bayes_steps,\
           snapshot_steps_features,\
           bayes_steps_features,\
           val_error,\
           step_error_pairs

def hyper_para_select_top_steps(hpara_log, 
                                val_snapshot_num, 
                                test_snapshot_num,
                                metric_idx):
    '''
    Argu.:
      hpara_log - [ dict{lr, batch, l2, ..., burn_in_steps}, [[step, tr_metric, val_metric, epoch]] ]
    '''
    hp_err = []
    
    for hp_epoch_err in hpara_log:
        hp_err.append([hp_epoch_err[0], hp_epoch_err[1], np.mean([k[2][metric_idx] for k in hp_epoch_err[1][:val_snapshot_num]])])
    
    # sorted_hp[0]: hyper-para with the best validation performance
    sorted_hp = sorted(hp_err, key = lambda x:x[-1])
    
    # -- top steps
    snapshot_steps = full_steps[:len(test_snapshot_num)]
    snapshot_steps_features = [ [k[1], k[2]] for k in sorted_hp[0][1][:len(bayes_steps)] ]
    
    best_hyper_para_dict = sorted_hp[0][0]
    # best hp, snapshot_steps, bayes_steps
    
    return best_hyper_para_dict,\
           snapshot_steps,\
           snapshot_steps_features,\

def hyper_para_select_bayeisan_steps(hpara_log, 
                                     val_snapshot_num, 
                                     test_snapshot_num,
                                     metric_idx):
    '''
    Argu.:
      hpara_log - [ dict{lr, batch, l2, ..., burn_in_steps}, [[step, tr_metric, val_metric, epoch]] ]
    '''
    hp_err = []
    
    for hp_epoch_err in hpara_log:
        hp_err.append([hp_epoch_err[0], hp_epoch_err[1], np.mean([k[2][metric_idx] for k in hp_epoch_err[1][:val_snapshot_num]])])
    
    # sorted_hp[0]: hyper-para with the best validation performance
    sorted_hp = sorted(hp_err, key = lambda x:x[-1])
    
    # -- bayes steps
    full_steps = [k[0] for k in sorted_hp[0][1]]
    
    tmp_burn_in_step = sorted_hp[0][0]["burn_in_steps"]
    bayes_steps = [i for i in full_steps if i >= tmp_burn_in_step]
    bayes_steps_features = [[k[1], k[2]] for k in sorted_hp[0][1] if k[0] >= tmp_burn_in_step]
        
    best_hyper_para_dict = sorted_hp[0][0]
    # best hp, snapshot_steps, bayes_steps
    
    return best_hyper_para_dict,\
           bayes_steps,\
           bayes_steps_features

# ----- data loader

class data_loader(object):
    
    def __init__(self,
                 x,
                 y,
                 batch_size,
                 num_ins,
                 num_src):
        '''
        Argu.:
          x: numpy array [S N T D]
          y: numpy array [N ...]
        '''
        np.random.seed(1)
        
        self.x = x
        self.y = y
        self.batch_size = int(batch_size)
        self.num_src = num_src
        
        self.num_batch = int(np.ceil(1.0*num_ins/int(batch_size)))
        
        self.ids = list(range(num_ins))
        np.random.shuffle(self.ids)
        self.batch_cnt = 0
        self.bool_last_batch = False
    
    def re_shuffle(self):
        self.batch_cnt = 0
        np.random.shuffle(self.ids)
        self.bool_last_batch = False
        
    def one_batch(self):
        
        if self.batch_cnt >= self.num_batch:
            return None, None, None
        else:
            # batch data
            batch_ids = self.ids[self.batch_cnt*int(self.batch_size):(self.batch_cnt+1)*int(self.batch_size)] 
            # shape: [S B T D]
            # B: number of data instances in one batch
            batch_x = [self.x[tmp_src][batch_ids] for tmp_src in range(self.num_src)]
            # [B 1]
            batch_y = self.y[batch_ids]
            
            self.batch_cnt += 1
            
            if self.batch_cnt >= self.num_batch:
                self.bool_last_batch = True
            
            return batch_x, batch_y, self.bool_last_batch