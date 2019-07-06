
class Check_Off(object):

   def __init__( self,cf,cluster_control,   io_control, handlers):
       self.cf = cf
       self.cluster_control = cluster_control
       self.io_control = io_control
       self.handlers = handlers
       
       
   


   def check_off (self, cf_handle, chainObj, parameters, event ):
        if event["name"] == "INIT":
           return

        temp = float(self.io_control.get_corrected_flow_rate())
        self.handlers["IRRIGATION_CONTROL"].hset("check_off",temp )
        if temp   > 1.:
           

           self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"check_off","details":{"flow_rate":temp },"level":"RED"})           
           return_value = "DISABLE"
        else:
           self.handlers["IRRIGATION_CONTROL"].hset("SUSPEND","OFF")
           
           self.handlers["IRRIGATION_PAST_ACTIONS"].push({"action":"check_off","details":{"flow_rate":temp },"level":"YELLOW"})   
           return_value = "DISABLE"
        return return_value
 
   
   def construct_chains( self , cf ):
       cf.define_chain("check_off_chain", False ) #tested
       cf.insert.log( "check off is active" )
       cf.insert.send_event("IRI_MASTER_VALVE_SUSPEND",None)
       cf.insert.one_step( self.io_control.disable_all_sprinklers  )
       cf.insert.one_step(  self.io_control.turn_off_master_valves  )# turn turn off master valve
       cf.insert.log( "wait to charge well tank" )
       cf.insert.wait_event_count(  count = 30 )
       cf.insert.one_step( self.io_control.turn_on_master_valves  )# turn turn on master valve
       cf.insert.one_step(  self.io_control.turn_off_cleaning_valves  )# turn turn off cleaning valve
       cf.insert.log( "wait 5 minutes to charge sprinkler lines" )
       cf.insert.wait_event_count( count = 300 ) 
       cf.insert.one_step(  self.check_off  )
       cf.insert.one_step(  self.io_control.turn_off_master_valves  )# turn turn off master valve
       cf.insert.send_event( "RELEASE_IRRIGATION_CONTROL")
       cf.insert.log( "check off is terminated" )
       cf.insert.send_event("IRI_MASTER_VALVE_RESUME",None)
       cf.insert.terminate(  )
       return  ["check_off_chain"]


   def construct_clusters( self, cluster, cluster_id, state_id ):
       cluster.define_state( cluster_id,  state_id,["check_off_chain"]  )

 
if __name__ == "__main__":
   pass