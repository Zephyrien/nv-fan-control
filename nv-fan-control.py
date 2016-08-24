#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sys import exit
from time import sleep
from subprocess import PIPE, Popen
from ast import literal_eval
from signal import signal, SIGINT, SIGTERM, SIGHUP
from os import environ,path
from threading import Thread, Lock, Event
from configparser import ConfigParser
from xdg.BaseDirectory import xdg_config_home
from logging import debug,info,DEBUG,INFO,basicConfig


EXECUTABLE='nvidia-settings'
conf_file='nv-fan-control/nvfan.conf'
# set default values
# temperature the GPU should have
default_curve={40: 40,
                    50: 43,
                    60: 50,
                    65: 65,
                    70: 95,
                    80: 99,
                    100: 100}
                    
class TemperatureCurve():
    """Class tu load and interpolate temperature curve
    """
    extended=[]
    def __init__(self, curve):                        
        # Calculating extended curve with tolerance
        self.curve=curve
    def gettargetspeed(self,x):        
        if x <= min(self.curve): return self.curve[min(self.curve)]
        try:            
            return(self.curve[x])            
        except KeyError:
            x1=sorted(self.curve.keys())
            y1=sorted(self.curve.values())    
            for k,v in enumerate(x1):
                if x >= x1[k] and x < x1[k+1]:
                    return(int(round((x-x1[k])/(x1[k+1]-x1[k])*(y1[k+1]-y1[k])+y1[k])))            
    

class StoppableThread(Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""
    def __init__(self,name):
        super(StoppableThread, self).__init__(name=name)
        self._stopper = Event()
    def stopit(self):       
        self._stopper.set()
    def stopped(self):
        return self._stopper.is_set()

class FanRegul(StoppableThread,TemperatureCurve):
    """Class to regulate temperature of one GPU
    """
    def __init__(self,gpuID, conf):
        name = "GPU#{}".format(gpuID)
        StoppableThread.__init__(self, name=name)  
        self.gpuID = gpuID           
        # Getting interval from conf (default=4)
        self.INTERVAL=conf.getinterval(name)
        # Getting tolerance from conf (default=4)
        self.TOL=conf.gettol(name)
        # Getting curve from conf       
        TemperatureCurve.__init__(self,conf.getcurve(name))
        # getting DISPLAY environment variable
        self.env=environ   
        if environ.get('DISPLAY')==None: self.env['DISPLAY']=':0'
        # getting initial temp and fan speed
        self.temp=self._get_temp()
        self.speed=self._get_fan_speed()        

    def stop(self):     
        """Stop and reset GPU configuration
        """
        info("Stopping... Resetting autofan mode for GPU#{}".format(self.gpuID))        
        cmd=["-a" , "[GPU:{}]/GPUFanControlState=0".format(self.gpuID)]
        self._execute(cmd)
        self.stopit()
        
    def _execute(self, arg):
        """ Run well formed command
        """
        cmd = [EXECUTABLE, "-c", self.env['DISPLAY']]        
        cmd.extend(arg)
        process = Popen(cmd,stdout=PIPE,stderr=PIPE,universal_newlines=True)
        process.wait()
        out, err = process.communicate()
        debug("STDOUT of {}: {}".format(EXECUTABLE,out))
        debug("STDERR of {}: {}".format(EXECUTABLE,err))        
        debug("Argument of {}: {}".format(EXECUTABLE,cmd))
        try:            
            return(int(out))
        except (ValueError, TypeError):
            return(0)       

    def _get_temp(self):
        """Return GPU temperature"""        
        cmd=["-t" , "-q", "[GPU:{}]/GPUCoreTemp".format(self.gpuID)]        
        self.temp=self._execute(cmd)
        debug("Measured temperature: " + str(self.temp))
        return(self.temp)

    def _get_fan_speed(self):
        """Get fan speed"""        
        cmd=["-t" , "-q", "[fan:{}]/GPUCurrentFanSpeed".format(self.gpuID)]
        self.speed=self._execute(cmd)      
        debug("Measured fan speed: " + str(self.speed))        
        return(self.speed)

    def _set_fan_speed(self,speed):
        """Set fan speed"""                
        cmd=["-a" , "[gpu:{}]/GPUFanControlState=1", "-a", "[fan:{}]/GPUTargetFanSpeed={}".format(self.gpuID,self.gpuID,speed)]        
        self._execute(cmd)
        self.speed=speed
            
    def _adjust(self):
        """ Adjust fan speed from temperature indication
        """        
        newspeed=self.gettargetspeed(self._get_temp())             
        debug("Temperature: {}, fanspeed (previous): {}%".format(self.temp,self.speed))        
        debug("Calculated new speed: {}%".format(newspeed))
        speed=self._get_fan_speed()
        # if variation < 2°C           
        if abs(speed - newspeed) > self.TOL:                                        
            info('Changing speed from {}% to {}% for GPU#{}'.format(self.speed,newspeed,self.gpuID))
            self._set_fan_speed(newspeed)        
        
    def run(self):
        """Entry of thread"""
        while not(self.stopped()):
            # Get lock to synchronize threads
            threadLock.acquire()            
            self._adjust()            
            # Free lock to release next thread
            threadLock.release()
            sleep(self.INTERVAL)

class NVConfig(ConfigParser):
    """Class to read and apply configuration
    """    
    def __init__(self):  
        ConfigParser.__init__(self)
        self.read(path.join(xdg_config_home, conf_file))        
        globalconf = self["Global"]
        self._gpu_count=globalconf.getint("nbGPU",1)    
        if globalconf.getboolean("Debug", False): 
            basicConfig(level=DEBUG, format='%(threadName)s : %(message)s')
        else:
            basicConfig(level=INFO, format='%(threadName)s : %(message)s')
        debug("Found {} GPU in conf".format(self._gpu_count))                               
    def _get_gpu_count(self):        
        """ Getting count of GPU from conf (default=1)"""
        return(self._gpu_count)
    def getinterval(self,name):
        """ Getting interval from conf (default=4)"""
        gpuconf=self[name]         
        return gpuconf.getint('Interval',4)        
        # Getting curve from conf
    def gettol(self,name):
        """Get tolerance from configuration"""
        gpuconf=self[name]        
        return gpuconf.getint('Tolerance',2)
    
    def getcurve(self,name):
        """Get curve from configuration"""
        gpuconf=self[name]
        try:            
            Curve=literal_eval(gpuconf.get("Curve"))
            debug("Using curve from config file: {}".format(Curve))
        except ValueError:            
            Curve=default_curve
            debug("Using default curve: {}".format(Curve))
        return Curve
    count = property(_get_gpu_count)
            
class GPUs(NVConfig):
    """Class to initialise GPUs and configuration
    also main class hold all thread for each GPU
    """
    threads = []    
    def __init__(self):        
        NVConfig.__init__(self)        
        for i in range (0, self.count):            
            gpu=FanRegul(i,self)
            self.threads.append(gpu)      
    def stop(self, signum, frame):
        """When receive interrupt SIGNINT or SIGTERM
        stopping"""
        for t in self.threads:            
            t.stop()
    def reload():
        """When receive interrupt SIGHUP
        reloading configuration"""
        info("Reloading")
    def run(self):
        """Start and wait for threads"""
        info("Starting...")         
        for t in self.threads:
            t.start()  
        for t in self.threads:
            t.join()

def main():    
    try:                     
        nv_gpus=GPUs()
        # Trap ^C
        signal(SIGINT, nv_gpus.stop)
        # Trap SIGTERM
        signal(SIGTERM, nv_gpus.stop)        
        signal(SIGHUP, nv_gpus.reload)
        nv_gpus.run()       
    except OSError as err:
        # executable not found on system          
        return("'" + EXECUTABLE + "' " + "was not found")

threadLock = Lock()

if __name__ == "__main__":
        exit(main())
