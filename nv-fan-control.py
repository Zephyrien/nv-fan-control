#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sys import exit
from time import sleep
from subprocess import check_output,CalledProcessError,STDOUT
from signal import signal, SIGINT, SIGTERM
from os import environ

EXECUTABLE='nvidia-settings'
# set default values
# temperature the GPU should have
TARGET_TEMP=65
# how much may the temperature vary from target (tolerance)
TEMP_TOL=2
# interval for checking temperature in sec
INTERVAL=2
# speed adjustment interval
ADJ_RATE=2
# minimum speed
SPEED_MIN=40
# maximum speed
SPEED_MAX=90

class NvidiaGpus():
    def __init__(self,nb_GPU):
        self._dictionnaire = {}
        self.nb_gpu = nb_GPU
        self.env=environ
        if environ.get('DISPLAY')==None: self.env['DISPLAY']=':0'
        for i in range (0, self.nb_gpu):
            self._dictionnaire[i] = self

    def __getitem__(self, index):
        """Used to get element on the dictionary with [index] syntax
        In case of multiple GPU"""
        self.idx=index
        if index >= len(self._dictionnaire): raise StopIteration
        return self._dictionnaire[index]

    def __setitem__(self, index, valeur):
        """Used to set element on the dictionary with [index] syntax
        In case of multiple GPU"""
        self.idx=index
        self._dictionnaire[index] = valeur

    def __iadd__(self, adj):
        """For increasing fan speed"""
        speed=self._get_fan_speed()
        if speed < SPEED_MAX: self._set_fan_speed(speed + adj)
        return(self)

    def __isub__(self,adj):
        """For decreasing  fan speed"""
        speed=self._get_fan_speed()
        if speed > SPEED_MIN: self._set_fan_speed(speed - adj)
        return(self)
		
    def __toint(self,value):
        try:
            return(int(value))
        except ValueError:
            return(0)
			
    def _temp(self):
        """Return GPU temperature"""
        cmd=str.split(EXECUTABLE + " -c " + self.env['DISPLAY'] + " -t -q [GPU:"+str(self.idx)+ "]/GPUCoreTemp")       
        return(self.__toint(check_output(cmd,stderr=STDOUT,universal_newlines=True).strip()))

    def _get_fan_speed(self):
        """Get fan speed"""
        cmd=str.split(EXECUTABLE + " -c " + self.env['DISPLAY'] + "-t -q [fan:"+str(self.idx)+ "]/GPUCurrentFanSpeed")        
        return(self.__toint(check_output(cmd,stderr=STDOUT,universal_newlines=True).strip()))

    def _set_fan_speed(self,speed):
        """Set fan speed"""
        cmd=str.split(EXECUTABLE + " -c " + self.env['DISPLAY'] + "-a [gpu:"+str(self.idx)+ "]/GPUFanControlState=1 -a [fan:"+str(self.idx)+ "]/GPUTargetFanSpeed="+str(speed))
        print(check_output(cmd,stderr=STDOUT,universal_newlines=True).strip())

    def stop(self, signum, frame):
        """Restoring GPU state on close or interupt"""
        print("Stopping...")
        for a in self:
            print("Restoring GPU#"+str(self.idx)+"...")
            cmd=str.split(EXECUTABLE + " -c " + self.env['DISPLAY'] + "-a [gpu:"+str(self.idx)+ "]/GPUFanControlState=0")
            print(check_output(cmd,stderr=STDOUT,universal_newlines=True).strip())
        raise StopIteration("The end.")

    fan_speed = property(_get_fan_speed, _set_fan_speed)
    temp=property(_temp)

def main():
    try:
        print("Starting...")
        nv_gpus = NvidiaGpus(1)
        # Trap ^C
        signal(SIGINT, nv_gpus.stop)
        # Trap SIGTERM
        signal(SIGTERM, nv_gpus.stop)
        while 1:
            for gpu in nv_gpus:
                if gpu.temp > TARGET_TEMP + TEMP_TOL:
                    gpu+=ADJ_RATE
                elif gpu.temp < TARGET_TEMP - TEMP_TOL:
                    gpu-=ADJ_RATE
            sleep(INTERVAL)
    except OSError as err:
        # executable not found on system
        return("'" + EXECUTABLE + "' " + "was not found")
    except CalledProcessError as e:
        # application error
        return("Could not execute '" + EXECUTABLE + "': " + str(NameError(e.output)))
    except StopIteration as the_end:
        # interupted by ^C or SIGTERM
        print(the_end)
        return(0)
    except Exception as e:
        # error
        return("Fatal error: " + str(e))
    return("It's not gonna happen")

if __name__ == "__main__":
        exit(main())
