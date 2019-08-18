

import time
import json
import os
from .valve_resistance_check_py3  import   Valve_Resistance_Check
from .clean_filter_py3            import   Clean_Filter
from .check_off_py3               import   Check_Off

from .irrigation_control_basic_py3      import   Irrigation_Control_Basic 
from core_libraries.irrigation_hash_control_py3 import get_flow_checking_limits
from core_libraries.irrigation_hash_control_py3 import get_cleaning_limits
from core_libraries.irrigation_hash_control_py3 import get_current_limits
from core_libraries.mqtt_current_monitor_interface_py3 import MQTT_Current_Monitor_Publish

class Irrigation_Queue_Management(object):

   def __init__(self,redis_site_data, handlers,cluster_id,cluster_control,cf,app_files,sys_files,manage_eto,irrigation_io,
                master_valves,cleaning_valves,measurement_depths,eto_management ,irrigation_hash_control,qs  ):
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
      self.eto_management = eto_management
      self.irrigation_hash_control = irrigation_hash_control
      self.redis_site_data = redis_site_data
      self.mqtt_flow_name = "MAIN_FLOW_METER"
      self.irrigation_excessive_flow_limits = get_flow_checking_limits(redis_site_data,qs)
      self.cleaning_limit      = get_cleaning_limits(redis_site_data,qs) 
      self.current_limit       = get_current_limits(redis_site_data,qs)
     
      self.mqtt_current_publish = MQTT_Current_Monitor_Publish(redis_site_data,"/REMOTES/CURRENT_MONITOR_1/",qs )
      
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
                                                             
      self.clean_filter = Clean_Filter(cf,cluster_control,irrigation_io, handlers,irrigation_hash_control )
      self.irrigation_control  =  Irrigation_Control_Basic(cf = cf,
                                                           cluster_control=cluster_control,
                                                           io_control = irrigation_io,
                                                           handlers=handlers,
                                                           app_files = app_files,
                                                           sys_files=sys_files,
                                                           manage_eto = manage_eto,
                                                           measurement_depths = measurement_depths,
                                                           irrigation_hash_control = irrigation_hash_control,
                                                           qs = qs,
                                                           redis_site = redis_site_data  )

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
      cf.insert.log("check irrigation queue")

      cf.insert.enable_chains(["operational_check"])
      cf.insert.wait_event_count( event = "IRRIGATION_OPERATION_OK" ,count = 1)
      cf.insert.one_step(cluster_control.disable_cluster, cluster_id )
      cf.insert.one_step(irrigation_io.disable_all_sprinklers )
      cf.insert.one_step(self.turn_on_power_relays)
      cf.insert.one_step(self.clear_max_currents)
      cf.insert.one_step(self.clear_json_object)
      cf.insert.send_event("IRI_MASTER_VALVE_RESUME",None)
      cf.insert.wait_event_count( count = 1 )
      cf.insert.log( "Checking Irrigation Queue" )
      cf.insert.wait_function( self.check_queue)
      
      cf.insert.one_step( self.dispatch_entry )
      cf.insert.wait_event_count( count = 1 )
      
      cf.insert.wait_event_count( event = "RELEASE_IRRIGATION_CONTROL" ,count = 1)
      cf.insert.one_step( self.delete_queue_entry )
      cf.insert.wait_event_count( count = 1 )
      cf.insert.log("RELEASE_IRRIGATION_CONTROL event received")
      cf.insert.reset()
      
      cf.define_chain("accumulate_cleaning_filter", True )
      #cf.insert.log("accumulate_cleaning_filer")      
      cf.insert.one_step(self.accumulate_cleaning_filter) 
      cf.insert.wait_event_count(event = "MINUTE_TICK")
      cf.insert.reset()

      cf.define_chain("check_excessive_current", True )
      #cf.insert.log("check_excessive_current")  
      cf.insert.verify_not_event_count_reset( event="RELEASE_IRRIGATION_CONTROL", count = 1, reset_event = None, reset_data = None ) 
      #cf.insert.one_step(self.send_mqtt_current_request)      
      cf.insert.wait_event_count( count = 10 )      
      cf.insert.assert_function_reset(self.check_excessive_current)
      cf.insert.log("excessive_current_found")
      cf.insert.send_event("IRI_CLOSE_MASTER_VALVE",None)
      cf.insert.send_event( "RELEASE_IRRIGATION_CONTROL")
      cf.insert.one_step(irrigation_io.disable_all_sprinklers )
      cf.insert.wait_event_count( count = 1 )
      cf.insert.reset()
 
      cf.define_chain("check_excessive_flow", True )
      #cf.insert.log("check_excessive_flow")
      cf.insert.verify_not_event_count_reset( event="RELEASE_IRRIGATION_CONTROL", count = 1, reset_event = None, reset_data = None )
      cf.insert.wait_function(self.monitor_excessive_flow)
      cf.insert.log("excessive_flow_found")
      cf.insert.send_event("IRI_CLOSE_MASTER_VALVE",None)
      cf.insert.send_event( "RELEASE_IRRIGATION_CONTROL")
      cf.insert.one_step(irrigation_io.disable_all_sprinklers )
      cf.insert.wait_event_count( count = 1 )
      cf.insert.reset()
      
      cf.define_chain("check_cleaning_valve", True )
      #cf.insert.log("check_cleaning_flow_meter")  
      cf.insert.verify_not_event_count_reset( event="RELEASE_IRRIGATION_CONTROL", count = 1, reset_event = None, reset_data = None ) 
       
      cf.insert.wait_event_count( count = 1,event ="MINUTE_TICK" )      
      cf.insert.assert_function_reset(self.check_cleaning_valve)
      cf.insert.log("excessive_cleaning_flow_found")
      cf.insert.send_event("IRI_CLOSE_MASTER_VALVE",None)
      cf.insert.send_event( "RELEASE_IRRIGATION_CONTROL")
      cf.insert.one_step(irrigation_io.disable_all_sprinklers )
      cf.insert.wait_event_count( count = 1 )
      cf.insert.reset()           
      
 
      cf.insert.one_step(self.clear_max_currents)
      cf.insert.one_step(self.clear_json_object) 

      
      cf.define_chain("operational_check", False )
      
      cf.insert.one_step(self.op_check_master_relay_json_object)
      cf.insert.enable_chains(["mqtt_power_device_check"])
      cf.insert.wait_event_count( event = "MQTT_POWER_DEVICE_OK" ,count = 1)
      
      cf.insert.one_step(self.op_check_mqtt_device_json_object)
      cf.insert.enable_chains(["mqtt_device_check"])
      cf.insert.wait_event_count( event = "MQTT_DEVICE_OK" ,count = 1)
      
      cf.insert.one_step(self.op_check_plc_device_json_object)
      cf.insert.enable_chains(["plc_device_check"])
      cf.insert.wait_event_count( event = "PLC_OPERATION_OK" ,count = 1)
      
      cf.insert.send_event( "IRRIGATION_OPERATION_OK")
      cf.insert.terminate()



      cf.define_chain("mqtt_power_device_check",False)     
      cf.insert.assert_function_terminate(  "MQTT_POWER_DEVICE_OK" ,None,self.check_master_relay) # False is pass
      cf.insert.one_step(self.turn_off_master_relay)
      cf.insert.wait_event_count(event = 10)
      cf.insert.one_step(self.turn_on_master_relay)
      cf.insert.wait_event_count( event="MINUTE_TICK",count = 1)
      cf.insert.reset()
      
      cf.define_chain("mqtt_device_check",False)     
      cf.insert.assert_function_terminate( "MQTT_DEVICE_OK" ,None,self.check_mqtt_power_relays) # False is pass
      cf.insert.one_step(self.turn_off_equipment_relay)
      cf.insert.wait_event_count(event = 10)
      cf.insert.one_step(self.turn_on_equipment_relay)
      cf.insert.wait_event_count( event="MINUTE_TICK",count = 1)
      cf.insert.verify_function_reset( None,None,self.check_equipment_power_level) # false is pass
      cf.insert.enable_chains(["serious_fault"])
      cf.insert.terminate()
    
      
      cf.define_chain("plc_device_check",False)     
      cf.insert.assert_function_terminate( "PLC_OPERATION_OK" ,None,self.check_plc_devices) # False is pass     
      cf.insert.wait_event_count(event = 10)     
      cf.insert.reset()
      
      
   
      
      cf.define_chain("serious_fault",False)
      cf.insert.one_step(self.op_check_serious_fault_json_object)
      #cf.insert.one_step(self.update_past_actions,"SERIOUS FAULT IRRIGATION SUSPENDED")
      cf.insert.halt() 
     
   def check_queue( self, cf_handle, chainObj, parameters, event):
   
   
       
       if event["name"] == "INIT":
          return False

       length =    self.handlers["IRRIGATION_PENDING_SERVER"].length()
       
       
       if int(length) > 0:
           return_value = True
          
       else:
           return_value = False
       
       return return_value 
       
   def delete_queue_entry(self,cf_handle, chainObj, parameters, event):
        self.handlers["IRRIGATION_CURRENT_CLIENT"].pop()
        self.clear_json_object()
        
   def dispatch_entry(self , cf_handle, chainObj, parameters, event ): 
 
 
       if event["name"] == "INIT":
          return
       #
       #
       #Checking to clean filter by accumulation
       #
       
       cleaning_sum      = self.irrigation_hash_control.hget("CLEANING_ACCUMULATION")
       if cleaning_sum > self.cleaning_limit:
           json_object = {}
           json_object["type"] = "CLEAN_FILTER"
           json_object["command"]     = "CLEAN_FILTER"
           json_object["schedule_name"]  = "CLEAN_FILTER"
           json_object["step"]           = 0
           json_object["run_time"]       = 0
           self.handlers["IRRIGATION_CURRENT_CLIENT"].push_front(json_object)
           details = "Schedule "+ json_object["schedule_name"] +" step "+str(json_object["step"] )+" Flow Induced Filter Cleaning"
           print(details)
           self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"load schedule data","details":details,"level":"YELLOW"})
 
       #
       json_object = self.handlers["IRRIGATION_PENDING_SERVER"].pop()
       json_object = json_object[1]
       if isinstance(json_object,str):
          json_object = json.loads(json_object)
      
       self.update_json_object(json_object)
       
       
       if json_object["type"] == "CHECK_OFF":
           self.handlers["IRRIGATION_CURRENT_CLIENT"].push(json_object)
           self.cluster_ctrl.enable_cluster_reset_rt( cf_handle, self.cluster_id, "CHECK_OFF" )
           return
       
       if json_object["type"] == "RESISTANCE_CHECK":
           self.handlers["IRRIGATION_CURRENT_CLIENT"].push(json_object)
           self.cluster_ctrl.enable_cluster_reset_rt( cf_handle, self.cluster_id,"MEASURE_RESISTANCE" )
           return
       
 

       if json_object["type"] == "CLEAN_FILTER":
           self.handlers["IRRIGATION_CURRENT_CLIENT"].push(json_object)
           self.clean_filter_flag = True
           self.cluster_ctrl.enable_cluster_reset_rt( cf_handle, self.cluster_id,"CLEAN_FILTER" )
           return
       if json_object["type"] == "RESET_SYSTEM_QUEUE":
           print("reset system")
           self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"RESET_SYSTEM_QUEUE","level":"RED"})
           time.sleep(5)
           os.system("reboot")
           return       
           
       if json_object["type"] == "IRRIGATION_STEP":
          
 
          json_object["restart"] =  False
          json_object["elasped_time"] = 0 
          self.handlers["IRRIGATION_CURRENT_CLIENT"].delete_all()
          if  json_object["eto_flag"] == True:
             runtime,flag,list_data = self.eto_management.determine_eto_management(json_object["run_time"], json_object["io_setup"] )
             json_object["run_time"] = runtime
             if runtime == 0:
                 details = "Schedule "+ json_object["schedule_name"] +" step "+str(json_object["step"] )+" IRRIGATION_ETO_RESTRICTION"

                 self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"load schedule data","details":details,"level":"YELLOW"})
                 self.cf.queue_event("RELEASE_IRRIGATION_CONTROL", 0)
                 return 
 
          
          self.handlers["IRRIGATION_CURRENT_CLIENT"].push(json_object)
          self.cluster_ctrl.enable_cluster_reset_rt( cf_handle, self.cluster_id,"DIAGNOSITIC_CONTROL" )
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


   def op_check_master_relay_json_object(self,*args):
      self.irrigation_hash_control.hset("SCHEDULE_NAME","CHECK_MASTER_RELAY")  
      self.irrigation_hash_control.hset("STEP",0)  
      self.irrigation_hash_control.hset("RUN_TIME",0)  
      self.irrigation_hash_control.hset("ELASPED_TIME",0)  
      self.irrigation_hash_control.hset("TIME_STAMP",time.time())

   def op_check_mqtt_device_json_object(self,*args):
      self.irrigation_hash_control.hset("SCHEDULE_NAME","CHECK_MQTT_DEVICES")  
      self.irrigation_hash_control.hset("STEP",0)  
      self.irrigation_hash_control.hset("RUN_TIME",0)  
      self.irrigation_hash_control.hset("ELASPED_TIME",0)  
      self.irrigation_hash_control.hset("TIME_STAMP",time.time())

   def op_check_plc_device_json_object(self,*args):
      self.irrigation_hash_control.hset("SCHEDULE_NAME","CHECK_PLC_DEVICES")  
      self.irrigation_hash_control.hset("STEP",0)  
      self.irrigation_hash_control.hset("RUN_TIME",0)  
      self.irrigation_hash_control.hset("ELASPED_TIME",0)  
      self.irrigation_hash_control.hset("TIME_STAMP",time.time())

   def op_check_serious_fault_json_object(self,*args):
      self.irrigation_hash_control.hset("SCHEDULE_NAME","SERIOUS EQUIPMENT CURRENT")  
      self.irrigation_hash_control.hset("STEP",0)  
      self.irrigation_hash_control.hset("RUN_TIME",0)  
      self.irrigation_hash_control.hset("ELASPED_TIME",0)  
      self.irrigation_hash_control.hset("TIME_STAMP",time.time())
      
   def clear_json_object(self,*args):
      self.irrigation_hash_control.hset("SCHEDULE_NAME","OFFLINE")  
      self.irrigation_hash_control.hset("STEP",0)  
      self.irrigation_hash_control.hset("RUN_TIME",0)  
      self.irrigation_hash_control.hset("ELASPED_TIME",0)  
      self.irrigation_hash_control.hset("TIME_STAMP",time.time())

   def update_json_object(self,json_object):
      self.irrigation_hash_control.hset("SCHEDULE_NAME",json_object["schedule_name"])  
      self.irrigation_hash_control.hset("STEP",1)  
      self.irrigation_hash_control.hset("RUN_TIME",json_object["run_time"])  
      self.irrigation_hash_control.hset("ELASPED_TIME",0)  
      self.irrigation_hash_control.hset("TIME_STAMP",time.time())

   def get_json_object(self):
      return_value = {}
      return_value["schedule_name"] = self.irrigation_hash_control.hget("SCHEDULE_NAME")  
      return_value["step"] = self.irrigation_hash_control.hget("STEP")  
      return_value["run_time"] = self.irrigation_hash_control.hget("RUN_TIME")  
      return_value["elasped_time"] = self.irrigation_hash_control.hget("ELASPED_TIME")  
      return return_value
#
#
#
#
#
#
   def check_master_relay(self,*parms):
      return False
      
      
   def turn_off_master_relay(self,*parms):
       pass
     
     
   def turn_on_master_relay(self,*parms):
         pass

   def check_mqtt_power_relays(self,*parms):
       return False
       
   def turn_off_equipment_relay(self,*parms):
      pass
            
   def turn_on_equipment_relay(self,*parms):
      pass
      
   def check_equipment_power_level(self,*parms):
      pass

   def check_plc_devices(self,*parms):
     pass



   def accumulate_cleaning_filter(self,cf_handle, chainObj, parameters, event):
       
       cleaning_sum      = self.irrigation_hash_control.hget("CLEANING_ACCUMULATION")     
       gpm               = self.handlers["MQTT_SENSOR_STATUS"].hget("MAIN_FLOW_METER")
       print("gpm",gpm)
       cleaning_sum += gpm
       self.irrigation_hash_control.hset("CLEANING_ACCUMULATION",cleaning_sum)

   def send_mqtt_current_request(self,cf_handle,chainObj,parameters,event):
       if event["name"] == "INIT":
          return "CONTINUE"
       else:
         self.mqtt_current_publish.read_max_currents()
         self.mqtt_current_publish.read_relay_states()         
         
         
   def turn_on_power_relays(self,cf_handle,chainObj,parameters,event):
       if event["name"] == "INIT":
          return "CONTINUE"
       else:
         self.clean_filter_flag = False
         self.mqtt_current_publish.enable_irrigation_relay()
         self.mqtt_current_publish.enable_equipment_relay()
         
   def clear_max_currents(self,cf_handle,chainObj,parameters,event):
       if event["name"] == "INIT":
          return "CONTINUE"
       else:
       
         self.mqtt_current_publish.clear_max_currents()
         
     

   def check_excessive_current(self,cf_handle, chainObj, parameters, event):
       self.send_mqtt_current_request(cf_handle, chainObj, parameters, event)
       max_current = self.irrigation_hash_control.hget("SLAVE_MAX_CURRENT")
       relay_state = self.irrigation_hash_control.hget("SLAVE_RELAY_STATE")
       return_value = False
       print("max_current",max_current)
       print("relay_state",relay_state)
       ref_time = time.time()
       plc_flag = False
       if max_current == None:
          plc_flag = True
       if relay_state == None:
         plc_flag = True
       if ref_time - max_current["timestamp"] > 60: # results greater than one minute ago
           plc_flag = True
       if ref_time - relay_state["timestamp"] >  60: # results greater than one minute ago
           plc_flag = True
          
       
       if max_current['MAX_EQUIPMENT_CURRENT'] > self.current_limit["EQUIPMENT"]:
          json_object = self.get_json_object()
          cf_handle.send_event("RELEASE_IRRIGATION_CONTROL",None) 
          details = "Schedule "+ json_object["schedule_name"] +" step "+str(json_object["step"] )+"Current: " + \
              str(max_current['MAX_EQUIPMENT_CURRENT'])+   "Excessive Slave Equipment Current"
          self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"Excessive Equipment Current","details":details,"level":"RED"})
          return_value =True
       
       if max_current['MAX_IRRIGATION_CURRENT'] > self.current_limit["IRRIGATION"]:
          json_object = self.get_json_object()
          cf_handle.send_event("RELEASE_IRRIGATION_CONTROL",None) 
          details = "Schedule "+ json_object["schedule_name"] +" step: "+str(json_object["step"] )+ \
                         "Current: "+str(max_current['MAX_IRRIGATION_CURRENT'])+" Excessive Irrigation Current"

          self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"Excessive Irrigation Current","details":details,"level":"RED"})
          return_value = True
       
       if relay_state["EQUIPMENT_STATE"] == False:
          json_object = self.get_json_object()
          cf_handle.send_event("RELEASE_IRRIGATION_CONTROL",None) 
          details = "Schedule "+ json_object["schedule_name"] +" step: "+str(json_object["step"] )+ \
                         "Current: "+str(relay_state["CURRENT_VALUE"])+" Equipment Relay Tripped"

          self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"Equipment Relay Tripped","details":details,"level":"RED"})
          return_value = True   

       if relay_state['IRRIGATION_STATE'] == False:
          json_object = self.get_json_object()
          cf_handle.send_event("RELEASE_IRRIGATION_CONTROL",None) 
          details = "Schedule "+ json_object["schedule_name"] +" step: "+str(json_object["step"] )+ \
                         "Current: "+str(relay_state["CURRENT_VALUE"])+" IRRIGATION Relay Tripped"

          self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"Irrigation Relay Tripped","details":details,"level":"RED"})
          return_value =True          
       if plc_flag == True:
         # add in get currents from plcs
         return_value = False
       return return_value
       
   def monitor_excessive_flow(self,cf_handle, chainObj, parameters, event):
       if event["name"] == "INIT":
         
          self.monitor_excessive_flow_count = 0
       if event["name"] == "MINUTE_TICK":
         
           
           gpm = self.handlers["MQTT_SENSOR_STATUS"].hget(self.mqtt_flow_name)
                     
           if gpm > self.irrigation_excessive_flow_limits["EXCESSIVE_FLOW_VALUE"]:
             self.monitor_excessive_flow_count += 1
           else:
             self.monitor_excessive_flow_count = 0
          
           if self.monitor_excessive_flow_count > self.irrigation_excessive_flow_limits["EXCESSIVE_FLOW_TIME"]:
              json_object = self.get_json_object()
              cf_handle.send_event("RELEASE_IRRIGATION_CONTROL",None) 
              details = "Schedule "+ json_object["schedule_name"] +" step "+str(json_object["step"] )+ \
                         "Flow:"+str(gpm)+" Excessive Irrigation Current"

              self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"Excessive Flow","details":details,"level":"RED"})
              return True
       return False
              
       

   def check_cleaning_valve(self,cf_handle, chainObj, parameters, event):
       if event["name"] == "INIT":  
          self.monitor_excessive_flow_count = 0
       else:
         if self.clean_filter_flag != True:
            gpm = self.handlers["MQTT_SENSOR_STATUS"].hget("CLEANING_FLOW_METER")
            
            if gpm != 0:
              json_object = self.get_json_object()
              details = "Schedule "+ json_object["schedule_name"] +" step "+str(json_object["step"] )+ \
                         "Flow:"+str(gpm)+" Excessive Cleaning Current"
              self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"Excessive Cleaning Valve Flow","details":details,"level":"RED"})
       return False       
