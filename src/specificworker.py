#
# Copyright (C) 2016 by YOUR NAME HERE
#
#    This file is part of RoboComp
#
#    RoboComp is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    RoboComp is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with RoboComp.  If not, see <http://www.gnu.org/licenses/>.
#

import sys, os, Ice, traceback, time, collections
import numpy as np
from pydynamixel import dynamixel
from pydynamixel import registers
from pydynamixel import packets

from mutex	import *
from threading import Lock
from PySide import *
from genericworker import *

ROBOCOMP = ''
try:
    ROBOCOMP = os.environ['ROBOCOMP']
except:
    print '$ROBOCOMP environment variable not set, using the default value /opt/robocomp'
    ROBOCOMP = '/opt/robocomp'
if len(ROBOCOMP)<1:
    print 'genericworker.py: ROBOCOMP environment variable not set! Exiting.'
    sys.exit()


preStr = "-I"+ROBOCOMP+"/interfaces/ --all "+ROBOCOMP+"/interfaces/"
Ice.loadSlice(preStr+"JointMotor.ice")
from RoboCompJointMotor import *
from jointmotorI import *

class SpecificWorker(GenericWorker):
    lisPos=collections.deque()
    bool=0;
    motorParams = []
    mutex_bus=QtCore.QMutex()
    L_L_Goals= []
    motorStateMapArray =[{},{}]
    motorStateMapReadOnly=motorStateMapArray[0]
    motorStateMapWrite = motorStateMapArray[0]
    lastIndex=0
    mutmState=mutex() #???
    serial_port = ""
    ListaPuntos = []
    serial_port = '/dev/ttyUSB0'

    def __init__(self, proxy_map):
        super(SpecificWorker, self).__init__(proxy_map)
        params = ()
        self.setParams(params)

        self.mutex_goals=QtCore.QMutex(QtCore.QMutex.Recursive)

        self.mutex_swap=QtCore.QMutex(QtCore.QMutex.Recursive)
        self.timer2 = QtCore.QTimer(self)
        self.timer.timeout.connect(self.readState)
        self.timer.start(200)
        self.timer2.timeout.connect(self.ComprobarLista2)
        self.timer2.start(50)

        self.maxGoals=6
        #self.timerS = QtCore.QTimer()
        #self.timerS.timeout.connect(self.readState)
        #self.timerS.start(250)


    def setParams(self, params):
        i=0
        with open("./etc/config","r") as f:
            for linea in f.readlines():

                if "Device" in linea:
                    sep=linea.split("=")
                    self.serial_port=sep[1].replace("\n","")
                else:
                    self.serial_port = '/dev/ttyUSB0'

                #if "NumMotors" in linea:
                    #separacion = linea.split("=")
                    #motorParams = separacion[1]
                if "Params_" in linea:
                    separacion = linea.split("=")

                    #Buscando ID
                    parametros = separacion[1].split(",")
                    name = parametros[0]
                    param = MotorParams()
                    param.name = name
                    param.busId = int (parametros[1])
                    param.invertedSign = parametros[2]
                    param.minPos = float(parametros[3])
                    param.maxPos = float(parametros[4])
                    param.zero = parametros[5]
                    param.maxVel = parametros[6]
                    param.stepsRev = parametros[7]
                    param.maxDegrees = float(parametros[8].replace("\n",""))

                    self.motorParams.append(param)

        self.bus = dynamixel.get_serial_for_url(self.serial_port)

        return True

    #@QtCore.Slot()
    #def compute(self):
        ##self.ComprobarLista()
        #self.ComprobarLista2()
        #self.readState()

#####################################################

    @QtCore.Slot()
    def readState(self):
        for x in self.motorParams:
            try:
                state = MotorState()
                with QtCore.QMutexLocker(self.mutex_bus):
                    state.pos = float(dynamixel.get_position(self.bus, x.busId, False, num_error_attempts=1))
                    state.pos=(state.pos) * (2.618 + 2.618) / 1023 -2.618
                    state.isMoving = dynamixel.get_is_moving(self.bus, x.busId, False, num_error_attempts=1)
                if x.invertedSign == "true":
                    state.pos=-state.pos
                state.tiempo=time.time()
                self.motorStateMapWrite[x.name] = state
                posV=self.motorStateMapReadOnly[x.name].pos
                tiempoV=self.motorStateMapReadOnly[x.name].tiempo
                if self.motorStateMapReadOnly!=self.motorStateMapWrite:
                    state.vel= (state.pos-posV)/(state.tiempo-tiempoV)
            except Exception, e:
                print "Fallo leyendo motores"
        with QtCore.QMutexLocker(self.mutex_swap):
            self.motorStateMapReadOnly=self.motorStateMapArray[self.lastIndex]
            self.lastIndex=self.lastIndex^1
            self.motorStateMapWrite=self.motorStateMapArray[self.lastIndex]


#
    # getAllMotorParams
    #
    def getAllMotorParams(self):
        return self.motorParams

    def mapear(self, x, in_min, in_max, out_min, out_max):
        return (x-in_min)*(out_max-out_min)/(in_max-in_min)+out_min

    def ComprobarLista(self):

        if len(self.lisPos) == 0:
            return
        try:
            m = self.lisPos.popleft()
            for x in self.motorParams:
                if x.name == m.name:
                    busId = x.busId
                    break
            pos = np.ushort((m.position + 2.618) * (1023 - 0) / (2.618 + 2.618))
            vel = np.ushort(m.maxSpeed)
            dynamixel.set_velocity(self.bus,busId, vel)
            dynamixel.set_position(self.bus, busId, pos)
            dynamixel.send_action_packet(self.bus)
        except Ice.Exception, e:
            traceback.print_exc()
            print e

    @QtCore.Slot()
    def ComprobarLista2(self):
        if len(self.L_L_Goals) == 0:
            return
        with QtCore.QMutexLocker(self.mutex_bus):
            try:
                for x in range(0, len(self.L_L_Goals)):
                    with QtCore.QMutexLocker(self.mutex_goals):
                        m = self.L_L_Goals.pop(0)
                    for goal in m:
                        for x in self.motorParams:
                            if x.name == goal.name:
                                busId = x.busId
                                break
                        if x.invertedSign == "true":
                            goal.position = -goal.position
                        pos = np.ushort((goal.position + 2.618) * (1023 - 0) / (2.618 + 2.618))
                        vel = np.ushort(goal.maxSpeed)
                        dynamixel.set_velocity(self.bus, busId, vel, False, num_error_attempts=1)
                        dynamixel.set_position(self.bus, busId, pos, False, num_error_attempts=1)
                    dynamixel.send_action_packet(self.bus)
            except Ice.Exception, e:
                traceback.print_exc()
                print e


    #
    # getAllMotorState
    #
    def getAllMotorState(self):
        mapAux={}
        vel=0
        pos=0
        for x in self.motorParams:
            with QtCore.QMutexLocker(self.mutex_swap):
                vel=self.motorStateMapReadOnly[x.name].vel
                pos=self.motorStateMapReadOnly[x.name].pos
            tiempo=time.time()
            state=MotorState()
            state.vel=vel
            state.pos=pos+vel * tiempo
            #state.pos=(state.pos) * (2.618 + 2.618) / 1023 -2.618
            mapAux[x.name]=state
            #print mapAux[x.name]
            #print mapAux[x.name].vel
        return mapAux


    #
    # getMotorParams
    #

    def getMotorParams(self, motor):

        pos=[x for x in self.motorParams if x.name == motor]
        return pos[0]

    # TODO GETMOTORSTATE
    # getMotorState
    #
    def getMotorState(self, motor):
        for x in self.motorParams:
            if x.name == motor:
                return self.motorStateMapReadOnly[motor]
        else:
            e = UnknownMotorException()
            e.what = "Error " + motor + " does not exist"
            raise e

    #
    # setSyncVelocity
    #
    def setSyncVelocity(self, listGoals):
        pass


    #
    # setZeroPos
    #
    def setZeroPos(self, name):
        pass


    #
    # getBusParams
    #
    def getBusParams(self):
        ret = BusParams()
        return ret


    #
    # setSyncZeroPos
    #
    def setSyncZeroPos(self):

        pass


    # TODO SETSYNCPOSITION
    # setSyncPosition
    #
    def setSyncPosition(self, listGoals):
        with QtCore.QMutexLocker(self.mutex_goals):
            if len(self.L_L_Goals)==self.maxGoals:
                e= HardwareFailedException()
                e.what="Demasiadas peticiones intentalo mas tarde"
                raise e
            else:
                self.L_L_Goals.append(listGoals)


    #
    # getMotorStateMap
    #
    def getMotorStateMap(self, mList):
        ret = MotorStateMap()
        for m in mList:
            if m in self.motorParams:
                ret[m]=self.motorStateMapReadOnly[m]
        return ret


    #
    # setPosition
    #
    def setPosition(self, goal):
        m = [x for x in self.motorParams if x.name == goal.name]
        if len(m)>0:
            position=(goal.position + 2.618) * (1023 - 0) / (2.618 + 2.618)
            pos=np.ushort(position)
            dynamixel.set_position(self.bus, (m[0].busId),pos)
            dynamixel.send_action_packet(self.bus)


    #
    # setVelocity
    #
    def setVelocity(self, goal):
        m = [x for x in self.motorParams if x.name == goal.name]
        if len(m)>0:

            pos=np.ushort(goal.velocity)
            dynamixel.set_velocity(self.bus, (m[0].busId),pos)
            dynamixel.send_action_packet(self.bus)

