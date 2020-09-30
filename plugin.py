# Manage ZoneMinder
# $Id$
#

"""
<plugin key="ZoneMinder" name="ZoneMinder Plugin" author="Morand" version="1.0.0" wikilink="" externallink="">
    <description>
        <h2>ZoneMinder</h2><br/>
            Manage ZoneMinder Cameras.
            KNOWN BUG: when detecting cameras the first time, just open one on domoticz page et update it. All other cameras are now working.
        <h3>Parameters</h3><br />
        <ul>
          <li>Address: IP of ZM</li>
          <li>Username: Username for ZM</li>
          <li>Password: Password for ZM</li>
          <li>Home: Portal path</li>
          <li>No Camera: if set to yes, do not add cameras, only add main state management.</li>
        </ul>
   </description>
    <params>
      <param field="Address" label="Address" width="150px" default=''/>
      <param field="Username" label="Username" width="150px" />
      <param field="Password" label="Password" width="150px" />
      <param field="Mode1" label="Type" width="150px" default="http">
           <options>
                <option label="HTTP" value="http"/>
                <option label="HTTPS" value="https"/>
            </options>
      </param>
      <param field="Mode2" label="Home" width="50px" default="zm"/>
      <param field="Mode3" label="No camera" width="50px">
            <options>
                <option label="True" value="true" default="True"/>
                <option label="False" value="false" />
            </options>
      </param>
      <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal"  default="true" />
            </options>
       </param>
    </params>
</plugin>
"""

import Domoticz
import sys
import os
sys.path.append('/usr/lib/python3/dist-packages')
import requests
import urllib
import json
import sqlite3
from urllib.parse import urlparse
import pyzm
import pyzm.api as zmapi


class  Camera:
    states={
        0:"Aucun",
        10:"Monitor",
        20:"Modect",
        30:"Record",
        40:"Modcord",
        50:"Nodect"
        }
    
    def __init__(self,cam):
        self._id=cam.id()        
        self._name=cam.name()
        self._snapShotPath='%s/cgi-bin/zms?mode=single&monitor=%d&user=%s&pass=%s'%(_plugin._baseURL,self._id,_plugin._username,_plugin._password)
        self._dev=Devices[(self._id+1)]
        Domoticz.Log('Camera %s (%s): %s'%(self._name,self._id,self._snapShotPath))

    def getCamStateId(state):
        for nval,sval in Camera.states.items():
            if sval==state:
                return nval
        return None

        
    def updateStatus(self):
        args={
            'force_reload': True # if True refreshes monitors
        }
        mon=_plugin._zmapi.monitors(args).find(self._id)
        state=Camera.getCamStateId(mon.function())
        if int(self._dev.nValue) != int(state):
            Domoticz.Log("Camera %d state change to %d/%s"%(self._id,int(state),mon.function()))
            self._dev.Update(sValue=str(state),nValue=int(state))

    def setState(self,state):
        options={'function':Camera.states[str(state)]}
        _plugin._zmapi.set_parameter(options)

    def getId(self):
        return self._id

    def getName(self):
        return  self._name
    
class ZoneMinderPlugin:

    def __init__(self):
        self._addr=None
        self._username=None
        self._password=None
        self._cameras={}
        self._baseURL=None
        self._zmapi=None
        self._states={}
        self._noCamera=False
        return

    def _updateMainStates(self):
        states=self._zmapi.states()
        def sortStates(obj):
            return obj.name()

        lst=states.list()
        lst.sort(key=sortStates)
        lvlNames=''
        nval=0
        cnval=nval
        csval=''
        for state in lst:
            nval+=10
            lvlNames=lvlNames+'|'+state.name()
            if state.active():
                Domoticz.Debug("Active state is %d/%s"%(nval,state.name()))
                cnval=nval
            csval=state.name()
            self._states[nval]=csval
                            
        dev=Devices[255]
        Domoticz.Debug("States: %s"%(lvlNames))
        Domoticz.Debug(dev.Options["LevelNames"])
        if dev.Options["LevelNames"] != lvlNames:
            newOptions=dev.Options
            newOptions["LevelNames"]=lvlNames
            Domoticz.Log("Update Main State Switch values:%s"%(lvlNames))
            dev.Update(nValue=cnval,sValue=csval,Options=newOptions)
        Domoticz.Debug("Current State: %d/%d"%(dev.nValue,cnval))
        if dev.nValue!=cnval:
            dev.Update(nValue=cnval,sValue=str(cnval))
        
    def onStart(self):
        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)
        Domoticz.Log("onStart called")
        DumpConfigToLog()
        self._addr=Parameters["Address"]
        self._username=Parameters["Username"]
        self._password=Parameters["Password"]
        self._type=Parameters["Mode1"]
        self._home=Parameters["Mode2"]
        if(Parameters["Mode3"]=="true"):
            self._noCamera=True
        self._baseURL='%s://%s/%s'%(self._type,self._addr,self._home)
        self._apiOptions = {
            'apiurl': self._baseURL+'/api',
            'portalurl': self._baseURL,
            'user': self._username,
            'password': self._password,
            'logger': None,
        }
        self._zmapi=zmapi.ZMApi(options=self._apiOptions)

        #Server informations
        infos= self._zmapi.version()
        Domoticz.Status(str(infos))

        if not 255 in Devices:
            Options = {"LevelActions": "|",
                       "LevelNames": "default",
                       "LevelOffHidden": "true",
                       "SelectorStyle": "1"}
            Domoticz.Device(Name="Main States",  Unit=255, TypeName="Selector Switch", Image=9,Options=Options).Create()
        self._updateMainStates()
            
        #Search new Cameras
        if self._noCamera==False:
            for camInfo in self._zmapi.monitors().list():
                cam=Camera(camInfo)
                self._cameras[(cam.getId()+1)]=cam
                if cam.getId()>=254:
                    Domoticz.Error("Camera ID for %s >= 254"%(cam.getName()))
                    return
                Domoticz.Log("Adding Camera %s"%(cam.getName()))
                #Selector switch values for new camera
                Options={"LevelActions":'||||||',
                         "LevelNames":"Aucun|Monitor|Modect|Record|Mocord|Nodect",
                         "LevelOffHidden":"true",
                         "SelectorStyle":"0"
                    }
                if not (cam.getId()+1) in Devices:
                    #create camera
                    Domoticz.Log("Creating Camera %s %d"%(cam.getName(),cam.getId()))
                    #Domoticz.Device(Name=cam.getName(), Unit=(cam.getId()+1),TypeName="Switch",Subtype=0,Switchtype=0).Create()
                    Domoticz.Device(Name=cam.getName(), Unit=(cam.getId()+1),TypeName="Selector Switch",Options=Options).Create()
                    dbConn=sqlite3.connect(os.getcwd()+'/domoticz.db')
                    dbCursor=dbConn.cursor()
                    url='%s/cgi-bin/zms?mode=single&monitor=%d&user=%s&pass=%s'%(self._home,cam.getId(),self._username,self._password)
                    query=""" INSERT INTO Cameras(Name,Address,Port,Protocol,ImageURL) VALUES (?,?,?,?,?) """
                    protocol=0
                    port=80
                    if self._type=='https':
                        protocol=1
                        port=443

                    data=(cam.getName(),self._addr,port,protocol,url)
                    dbCursor.execute(query,data)
                    dbConn.commit()
                    lastId=dbCursor.lastrowid
                    dbCursor.execute("INSERT INTO CamerasActiveDevices (CameraRowID,DevSceneRowID,DevSceneType,DevSceneDelay,DevSceneWhen) VALUES (%d,%d,0,0,0);"%(lastId,Devices[(cam.getId()+1)].ID))
                    dbConn.commit()
                    dbConn.close()
        return

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")
        self._updateMainStates()
        for cam in self._cameras:
            self._cameras[cam].updateStatus()
                    
    def onDeviceAdded(self):
        Domoticz.Log("Adding device")
        return

    def onStop(self):
        return

    def onCommand(self,Unit,Command,Level,Hue):
        dev=Devices[Unit]
        if Unit==255:
            Domoticz.Debug("onCommand: %s (%d/%s)"%(str(self._states),int(Level),str(Level)))
            self._zmapi.set_state(self._states[int(Level)])
        else:
            cam=self._cameras[Unit]
            cam.setState(Level)
        pass
        
global _plugin
_plugin = ZoneMinderPlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def  onDeviceAdded():
    global _plugin
    _plugin.onDeviceAdded()
    # Generic helper functions

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
            Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
