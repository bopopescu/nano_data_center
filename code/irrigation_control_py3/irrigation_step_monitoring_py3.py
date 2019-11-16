#Note -- deal with limits
#note -- deal with short irrigation sequences
#note -- deal with bad histories

import time
import math
from statistics import mean
from statistics import median
from statistics import pstdev

class Irrigation_Step_Monitoring(object):


   def __init__(self,handlers,manage_eto,io_manager,cf,irrigation_hash_control,qs,redis_site):
       self.manage_eto = manage_eto
       self.handlers   = handlers
       self.io_manager = io_manager
       self.cf         = cf
       self.irrigation_hash_control = irrigation_hash_control
       query_list = []
       query_list = qs.add_match_relationship( query_list,relationship="SITE",label=redis_site["site"] )
       query_list = qs.add_match_relationship( query_list,relationship="IRRIGIGATION_SCHEDULING_CONTROL",label="IRRIGIGATION_SCHEDULING_CONTROL" )
       query_list = qs.add_match_terminal( query_list, 
                                        relationship =  "IRRIGATION_LOGGING",label = "IRRIGATION_LOGGING" )
       data_sets,data_list = qs.match_list(query_list)                 
       data = data_list[0]
       self.log_length = data["log_length"]
       self.settling_time = data["settling_time"]      
       self.key_list = ["WELL_PRESSURE",
                        "EQUIPMENT_CURRENT",
                        "IRRIGATION_CURRENT",
                        "MAIN_FLOW_METER",
                        "CLEANING_FLOW_METER",
                        "INPUT_PUMP_CURRENT",
                        "OUTPUT_PUMP_CURRENT"]
       self.sensor_list = ["WELL_PRESSURE",
                           "EQUIPMENT_CURRENT",
                           "IRRIGATION_CURRENT",
                           "MAIN_FLOW_METER",
                           "CLEANING_FLOW_METER",
                           "INPUT_PUMP_CURRENT",
                           "OUTPUT_PUMP_CURRENT"
                          ]

   


   def initialize_logging(self,json_object):
       self.handlers["IRRIGATION_TIME_HISTORY"].delete_all()  # for test purposes only
       self.working_key = self.form_key(json_object)
       self.time_history = self.handlers["IRRIGATION_TIME_HISTORY"].hget(self.working_key)
      
       if self.time_history == None:
          self.time_history = []
       
       self.time_history.append(self.format_entry())
      
       if len(self.time_history) > self.log_length:
           self.time_history = self.time_history[1:]

       
           
       


   def step_logging(self, json_object):
       working_entry = self.time_history[-1]
       self.add_new_data(working_entry,self.get_new_data())

       
       
   def finalize_logging(self):
       working_entry = self.time_history[-1]
       self.time_history[-1] = self.sumarize_data(working_entry)
       print(self.time_history)
       self.handlers["IRRIGATION_TIME_HISTORY"].hset(self.working_key,self.time_history)


   def form_key(self,json_object):

     
      key = ""
      for item in json_object["io_setup"]:
         if key == "":
             key = key+item["remote"]+":"+str(item["bits"][0])
         else:
              key = key+"/"+item["remote"]+":"+str(item["bits"][0]) 
      return key
      
   def format_entry(self):
      entry = {}
      entry["mean"] = {}
      entry["sd"]  = {}
      entry["data"] = []
     
      return entry
      
   def get_new_data(self):
      new_data = {}
      for i in range(0,len(self.key_list)):
         new_data[self.key_list[i]] = self.irrigation_hash_control.hget(self.sensor_list[i])
      return new_data
      
   def add_new_data(self,entry,new_data):
      entry["data"].append(new_data)   
      
   def sumarize_data(self,working_entry):
       print(working_entry)
       for i in self.key_list:
          working_entry["mean"][i] = mean(working_entry["data"][i][self.settling_time:])
          working_entry["sd"][i]  = pstdev(working_entry["data"][i][self.settling_time:])
          form of data  need to restructure
          [{'IRRIGATION_CURRENT': 0.1420000046491623, 'MAIN_FLOW_METER': 0.0, 'WELL_PRESSURE': 55.50770163536072, 'OUTPUT_PUMP_CURRENT': -0.07856567700703923, 'EQUIPMENT_CURRENT': 0.3908296525478363, 'INPUT_PUMP_CURRENT': -0.40452753504117345, 'CLEANING_FLOW_METER': 0.0}, {'IRRIGATION_CURRENT': 0.1420000046491623, 'MAIN_FLOW_METER': 0.0, 'WELL_PRESSURE': 55.48233985900879, 'OUTPUT_PUMP_CURRENT': -0.09210189183553102, 'EQUIPMENT_CURRENT': 0.3908296525478363, 'INPUT_PUMP_CURRENT': -0.4483915865421294, 'CLEANING_FLOW_METER': 0.0}, {'IRRIGATION_CURRENT': 0.1420000046491623, 'MAIN_FLOW_METER': 0.0, 'WELL_PRESSURE': 55.62085509300232, 'OUTPUT_PUMP_CURRENT': -0.0769250591595974, 'EQUIPMENT_CURRENT': 0.3908296525478363, 'INPUT_PUMP_CURRENT': -0.4002446929613754, 'CLEANING_FLOW_METER': 0.0}, {'IRRIGATION_CURRENT': 0.1420000046491623, 'MAIN_FLOW_METER': 0.0, 'WELL_PRESSURE': 55.464619398117065, 'OUTPUT_PUMP_CURRENT': -0.07806549469629911, 'EQUIPMENT_CURRENT': 0.3908296525478363, 'INPUT_PUMP_CURRENT': -0.39949839313824986, 'CLEANING_FLOW_METER': 0.0}, {'IRRIGATION_CURRENT': 0.1420000046491623, 'MAIN_FLOW_METER': 0.0, 'WELL_PRESSURE': 53.26618552207947, 'OUTPUT_PUMP_CURRENT': -0.1388791203498841, 'EQUIPMENT_CURRENT': 0.3908296525478363, 'INPUT_PUMP_CURRENT': -0.6025888025760656, 'CLEANING_FLOW_METER': 0.0}, {'IRRIGATION_CURRENT': 0.1420000046491623, 'MAIN_FLOW_METER': 0.0
          
 
