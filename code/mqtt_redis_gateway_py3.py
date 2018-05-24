#
#  MQTT To Redis Bridge
#
#
#
import json
import msgpack
import base64
import redis

from redis_support_py3.mqtt_to_redis_py3 import MQTT_TO_REDIS_BRIDGE_STORE
import paho.mqtt.client as mqtt
import ssl

class MQTT_Redis_Bridge(object):
   
   def __init__(self,redis_site_data):
       self.redis_site_data = redis_site_data
       self.mqtt_bridge = MQTT_TO_REDIS_BRIDGE_STORE(redis_site_data,100)
       
       self.client = mqtt.Client(client_id="", clean_session=True, userdata=None,  transport="tcp")
       self.client.tls_set(certfile= "/home/pi/mosquitto/certs/client.crt", keyfile= "/home/pi/mosquitto/certs/client.key", cert_reqs=ssl.CERT_NONE )
       
       redis_handle_pw = redis.StrictRedis(redis_site_data["host"], 
                                           redis_site_data["port"], 
                                           db=redis_site_data["redis_password_db"], 
                                           decode_responses=True)
                                          
       self.client.username_pw_set("pi", redis_handle_pw.hget("mosquitto_local","pi"))
       
       self.client.on_connect = self.on_connect
       self.client.on_message = self.on_message
       self.client.connect(redis_site_data["mqtt_server"],redis_site_data["mqtt_port"], 60)
       self.client.loop_forever()

   def on_connect(self,client, userdata, flags, rc):
       print("Connected with result code "+str(rc),self.redis_site_data["mqtt_topic"])
       self.client.subscribe(self.redis_site_data["mqtt_topic"])

# The callback for when a PUBLISH message is received from the server.
   def on_message(self, client, userdata, msg):
       print(msg.topic+" "+str(msg.payload))
       self.mqtt_bridge.store_mqtt_data(msg.topic,msg.payload)


if __name__ == "__main__":
   import time
   from threading import Thread
   from redis_support_py3.mqtt_client_py3 import MQTT_CLIENT
   def test_driver(redis_site_data):
       
       MQTT_Redis_Bridge(redis_site_data)
   
   file_handle = open("system_data_files/redis_server.json",'r')
   data = file_handle.read()
   file_handle.close()
      
   redis_site_data = json.loads(data)
   
   server = Thread(target=test_driver,args=(redis_site_data,))
   server.start()
   
   mqtt_client = MQTT_CLIENT(redis_site_data)
   print("client connected",mqtt_client.connect())
   print("starting to publish")
   print("message published",mqtt_client.publish("REMOTES/SLAVE:1/TEMPERATURE:Case",72))
   while True:
      pass