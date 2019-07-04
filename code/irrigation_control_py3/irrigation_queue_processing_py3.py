


import json
import os
from .valve_resistance_check_py3  import   Valve_Resistance_Check
from .clean_filter_py3            import   Clean_Filter
from .check_off_py3               import   Check_Off
from .irrigation_control_basic_py3      import   Irrigation_Control_Basic 



class Irrigation_Queue_Management(object):

   def __init__(self,handlers,cluster_id,cluster_control,cf,app_files,sys_files,manage_eto,irrigation_io,master_valves,cleaning_valves,measurement_depths):
      self.handlers = handlers
      self.cluster_id = cluster_id
      self.cluster_ctrl = cluster_control
      self.cf = cf
      self.app_files = app_files
      self.sys_files = sys_files
      self.manage_eto = manage_eto
      self.irrigation_io = irrigation_io
      self.master_valves = master_valves
      self.cleaning_valves = cleaning_valves
      self.measurement_depths = measurement_depths
     
      self.check_off     = Check_Off(cf=cf,cluster_control=cluster_control,io_control=irrigation_io, handlers=handlers )   
      self.measure_valve_resistance = Valve_Resistance_Check(cf =cf,
                                                             cluster_control = cluster_control,
                                                             io_control = irrigation_io, 
                                                             handlers = handlers,
                                                             app_files = app_files, 
                                                             sys_files = sys_files,
                                                             master_valves = master_valves,
                                                             cleaning_valves = cleaning_valves,
                                                             measurement_depths = measurement_depths )
                                                             
      self.clean_filter = Clean_Filter(cf,cluster_control,irrigation_io, handlers )
      self.irrigation_control  =  Irrigation_Control_Basic(cf = cf,
                                                           cluster_control=cluster_control,
                                                           io_control = irrigation_io,
                                                           handlers=handlers,
                                                           app_files = app_files,
                                                           sys_files=sys_files,
                                                           manage_eto = manage_eto,
                                                           measurement_depths = measurement_depths )

      self.chain_list    = []
      self.chain_list.extend(self.check_off.construct_chains(cf))
      self.chain_list.extend(self.measure_valve_resistance.construct_chains(cf))
      self.chain_list.extend(self.clean_filter.construct_chains(cf))
       
      self.chain_list.extend(self.irrigation_control.construct_chains(cf))

      cluster_control.define_cluster( cluster_id, self.chain_list, [])
      self.check_off.construct_clusters( cluster_control, cluster_id,"CHECK_OFF" )
      self.measure_valve_resistance.construct_clusters(cluster_control, 
                                                     cluster_id,"MEASURE_RESISTANCE" )
      self.clean_filter.construct_clusters( cluster_control, cluster_id,"CLEAN_FILTER" )
      
      self.irrigation_control.construct_clusters( cluster_control, cluster_id,"DIAGNOSITIC_CONTROL" )
         
  
     

 
  




      cf.define_chain("QC_Check_Irrigation_Queue", True )
      cf.insert.one_step(cluster_control.disable_cluster, cluster_id )
      cf.insert.one_step(irrigation_io.disable_all_sprinklers )
      cf.insert.send_event("IRI_MASTER_VALVE_RESUME",None)
      cf.insert.wait_event_count( count = 1 )
      cf.insert.log( "Checking Irrigation Queue" )
      cf.insert.wait_function( self.check_queue)
      cf.insert.one_step( self.dispatch_entry )
      #cf.insert.send_event("RELEASE_IRRIGATION_CONTROL") # for diagnostics
      cf.insert.wait_event_count( event = "RELEASE_IRRIGATION_CONTROL" ,count = 1)
      cf.insert.wait_event_count( count = 1 )
      cf.insert.log("RELEASE_IRRIGATION_CONTROL event received")
      cf.insert.reset()

 
      
      
      
           



       
   def check_queue( self, cf_handle, chainObj, parameters, event):
   
   
   
       if event["name"] == "INIT":
          return False

       length =    self.handlers["IRRIGATION_PENDING_SERVER"].length()
       
       
       if int(length) > 0:
           return_value = True
       else:
           return_value = False
       
       return return_value 
       
       
   def dispatch_entry(self , cf_handle, chainObj, parameters, event ): 
 
 
       if event["name"] == "INIT":
          return
 
       json_object = self.handlers["IRRIGATION_PENDING_SERVER"].pop()
       json_object = json_object[1]
       if isinstance(json_object,str):
          json_object = json.loads(json_object)
       print("dispatch_entry",json_object)
       
       
       if json_object["type"] == "CHECK_OFF":
           self.cluster_ctrl.enable_cluster_reset_rt( cf_handle, self.cluster_id, "CHECK_OFF" )
           return
       
       if json_object["type"] == "RESISTANCE_CHECK":
           print("made it here resistance check")
           self.cluster_ctrl.enable_cluster_reset_rt( cf_handle, self.cluster_id,"MEASURE_RESISTANCE" )
           return
       
 

       if json_object["type"] == "CLEAN_FILTER":
          
           self.cluster_ctrl.enable_cluster_reset_rt( cf_handle, self.cluster_id,"CLEAN_FILTER" )
           return
       if json_object["type"] == "RESET_SYSTEM_QUEUE":
           print("reset system")
           self.cf.queue_event("RELEASE_IRRIGATION_CONTROL", 0)
    
           #os.system("reset")
           return       
           
       if json_object["type"] == "IRRIGATION_STEP":
          print("made it here irrigation step")
          self.cf.queue_event("RELEASE_IRRIGATION_CONTROL", 0)
          return
          json_object["restart"] =  False
          json_object["elasped_time"] = 0 
          self.handlers["IRRIGATION_CURRENT_CLIENT"].delete_all()
          if  json_object["eto_flag"] == True:
             runtime,flag,list_data = self.eto_management.determine_eto_management(json_object["run_time"], json_object["io_setup"] )
             json_object["run_time"] = runtime
             if runtime == 0:
                 details = "Schedule "+ json_object["schedule_name"] +" step "+str(json_object["step"] )+" IRRIGATION_ETO_RESTRICTION"
                 print(details)
                 self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"load schedule data","details":details,"level":"YELLOW"})
                 return
 
             
          #handlers["IRRIGATION_PENDING_CLIENT"].push(json_object)
          #self.cluster_ctrl.enable_cluster_reset_rt( cf_handle, self.cluster_id,"DIAGNOSITIC_CONTROL" )
       return "DISABLE"

   def clear_redis_irrigate_queue( self,*args ):
       self.handlers["IRRIGATION_CURRENT_CLIENT"].delete_all()
       self.handlers["IRRIGATION_PENDING_SERVER"].delete_all()




   def terminate_operation( self):
       self.clear_redis_irrigate_queue()
       self.cf.disable_chain_base(["QC_Check_Irrigation_Queue"] )
       self.cluster_ctrl.disable_cluster_rt( self.cf,self.cluster_id)

   def suspend_operation( self ,*args):
       self.cf.suspend_chain_code(["QC_Check_Irrigation_Queue"])
       self.cluster_ctrl.suspend_cluster_rt(self.cf , self.cluster_id)

   def resume_operation( self, *args ):
       self.cf.resume_chain_code(["QC_Check_Irrigation_Queue"])
       self.cluster_ctrl.resume_cluster_rt( self.cf,self.cluster_id)

   def restart_operation( self,*args):
       self.cf.enable_chain_code(["QC_Check_Irrigation_Queue"])
       self.cluster_ctrl.disable_cluster_rt( self.cf,self.cluster_id)

   def skip_operation( self,*args ):
       self.cf.send_event("RELEASE_IRRIGATION_CONTROL",None)       
      
