#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sys import exit,stderr
from time import sleep
from subprocess import check_output,CalledProcessError,STDOUT,DEVNULL, PIPE, Popen
#import subprocess
from signal import signal, SIGINT, SIGTERM
from os import environ
import threading
import logging

EXECUTABLE='nvidia-settings'
# set default values
# temperature the GPU should have
TOL=2
# interval for checking temperature in sec
INTERVAL=4

curve = {40: 40,
        50: 43,
        60: 50,
        65: 65,
        70: 95,
        80: 99,
        100: 100}
        
class TemperatureCurve():
        extended=[]
        def __init__(self, curve):                        
            # Calculating extended curve with tolerance
            sortedcurve=sorted(curve.items())
            for k, v in enumerate(sortedcurve):
                try:
                    X_1=sortedcurve[k]
                    X_2=sortedcurve[k+1]
                    for i in range(X_1[0],X_2[0]):                                             
                        self.extended.append((i, int((i-X_1[0])/(X_2[0]-X_1[0])*(X_2[1]-X_1[1])+X_1[1])))
                except IndexError:            
                    pass

        def gettargetspeed(self, temp):            
            for k,v in self.extended:
                if temp<=k: return v
            return(extended)


class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self,name):
        super(StoppableThread, self).__init__(name=name)
        self._stopper = threading.Event()

    def stopit(self):       
        self._stopper.set()

    def stopped(self):
        return self._stopper.is_set()

class NvidiaGpus(StoppableThread,TemperatureCurve):       
    def __init__(self,gpuID):
        #super(self.__class__, self).__init__(self)        
        StoppableThread.__init__(self, name="GPU#" + str(gpuID))
        TemperatureCurve.__init__(self,curve)
        self.gpuID = gpuID        
        self.env=environ        
        if environ.get('DISPLAY')==None: self.env['DISPLAY']=':0'   
        self.temp=self._get_temp()
        self.speed=self._get_fan_speed()        

    def stop(self):        
        print("Stopping... Resetting autofan mode for GPU#"+str(self.gpuID))        
        cmd=[EXECUTABLE, "-c", self.env['DISPLAY'], "-a" , "[GPU:"+str(self.gpuID)+ "]/GPUFanControlState=0"]
        self._execute(cmd)
        self.stopit()
        
    def _execute(self, cmd):    
        process = Popen(cmd,stdout=PIPE,stderr=PIPE,universal_newlines=True)
        process.wait()
        out, err = process.communicate()
        logging.debug("STDOUT of {}: {}".format(EXECUTABLE,out))
        logging.debug("STDERR of {}: {}".format(EXECUTABLE,err))        
        logging.debug("Argument of {}: {}".format(EXECUTABLE,cmd))
        try:            
            return(int(out))
        except (ValueError, TypeError):
            return(0)       

    def _get_temp(self):
        """Return GPU temperature"""        
        cmd=[EXECUTABLE, "-c", self.env['DISPLAY'], "-t" , "-q", "[GPU:"+str(self.gpuID)+ "]/GPUCoreTemp"]        
        self.temp=self._execute(cmd)
        logging.debug("Measured temperature: " + str(self.temp))
        return(self.temp)

    def _get_fan_speed(self):
        """Get fan speed"""        
        cmd=[EXECUTABLE, "-c", self.env['DISPLAY'], "-t" , "-q", "[fan:"+str(self.gpuID)+ "]/GPUCurrentFanSpeed"]
        self.speed=self._execute(cmd)      
        logging.debug("Measured fan speed: " + str(self.speed))
        return(self.speed)

    def _set_fan_speed(self,speed):
        """Set fan speed"""                
        cmd=[EXECUTABLE, "-c", self.env['DISPLAY'], "-a" , "[gpu:"+str(self.gpuID)+ "]/GPUFanControlState=1", "-a", "[fan:"+str(self.gpuID)+ "]/GPUTargetFanSpeed="+str(speed)]        
        self._execute(cmd)
        self.speed=speed
        
    def _adjust_by_target(self):
        self.temp=self._temp()
        self.speed=self._get_fan_speed()
        if self.temp > TARGET_TEMP + TOL:
            if self.speed < SPEED_MAX: self._set_fan_speed(self.speed + ADJ_RATE)                    
        elif self.temp < TARGET_TEMP - TOL:
            if self.speed > SPEED_MIN: self._set_fan_speed(self.speed - ADJ_RATE)
            
    def _adjust_by_curve(self):        
        # Old value                
        newspeed=self.gettargetspeed(self.temp)             
        logging.debug("Temperature: {}, fanspeed (previous): {}%".format(self.temp,self.speed))        
        logging.debug("Calculated new speed: " + str(newspeed))
        speed=self._get_fan_speed()
        # if variation < 2°C        
        if abs(speed - newspeed) > TOL:                                        
            logging.info('Changing speed from {}% to {}% for GPU#{}'.format(self.speed,newspeed,self.gpuID))
            self._set_fan_speed(newspeed)        
        
    def run(self):                
        while not(self.stopped()):
            # Get lock to synchronize threads
            threadLock.acquire()
            #self._adjust_by_target()   
            self._adjust_by_curve()            
            # Free lock to release next thread
            threadLock.release()
            sleep(INTERVAL)        

    fan_speed = property(_get_fan_speed, _set_fan_speed)

class GPUs():
    threads = []
    def __init__(self,count):        
        for i in range (0, count):                                    
            gpu=NvidiaGpus(i)
            self.threads.append(gpu)        
    def _startall(self):        
        for t in self.threads:
            t.start()        
    def stop(self, signum, frame):
        for t in self.threads:            
            t.stop()
    def run(self):
       print("Starting...")         
       for t in self.threads:
            t.start()  
       for t in self.threads:
            t.join()

def main():
    logging.basicConfig(level=logging.INFO, format='%(threadName)s : %(message)s')
    try:                     
        nv_gpus=GPUs(1)
        # Trap ^C
        signal(SIGINT, nv_gpus.stop)
        # Trap SIGTERM
        signal(SIGTERM, nv_gpus.stop)        
        nv_gpus.run()       
    except OSError as err:
        # executable not found on system  
        
        return("'" + EXECUTABLE + "' " + "was not found")

threadLock = threading.Lock()

if __name__ == "__main__":
        exit(main())
