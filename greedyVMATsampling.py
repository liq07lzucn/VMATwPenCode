#!/home/wilmer/anaconda3/bin/python

__author__ = 'wilmer'
try:
    import mkl
    have_mkl = True
    print("Running with MKL Acceleration")
except ImportError:
    have_mkl = False
    print("Running with normal backends")

import glob, os
import numpy as np
import scipy.io as sio
from scipy import sparse
from scipy.optimize import minimize
import time
import math
import pylab
import matplotlib.pyplot as plt
from itertools import chain
from numba import jit
from multiprocessing import Pool
from functools import partial
import random
import sys

# Set of apertures starting with 16 that are well spread out.
kappa = [6, 17, 28, 39, 50, 61, 72, 83, 94, 105, 116, 127, 138, 149, 160, 171, 11, 22, 33, 44, 55, 66, 77, 88, 99, 110, 121, 132, 143, 154, 165, 1, 175, 14, 25, 36, 47, 58, 69, 80, 91, 102, 113, 124, 135, 146, 157, 168, 3, 8, 19, 30, 41, 52, 63, 74, 85, 96, 107, 118, 129, 140, 151, 162, 172, 176, 0, 2, 4, 5, 7, 9, 10, 12, 13, 15, 16, 18, 20, 21, 23, 24, 26, 27, 29, 31, 32, 34, 35, 37, 38, 40, 42, 43, 45, 46, 48, 49, 51, 53, 54, 56, 57, 59, 60, 62, 64, 65, 67, 68, 70, 71, 73, 75, 76, 78, 79, 81, 82, 84, 86, 87, 89, 90, 92, 93, 95, 97, 98, 100, 101, 103, 104, 106, 108, 109, 111, 112, 114, 115, 117, 119, 120, 122, 123, 125, 126, 128, 130, 131, 133, 134, 136, 137, 139, 141, 142, 144, 145, 147, 148, 150, 152, 153, 155, 156, 158, 159, 161, 163, 164, 166, 167, 169, 170, 173, 174, 177]
WholeCircle = False

rootFolder = '/media/wilmer/datadrive'
#rootFolder = '/home/wilmer/Documents/Troy_BU'
readfolder = rootFolder + '/Data/DataProject/HN/'
readfolderD = readfolder + 'Dij/'
outputfolder = '/home/wilmer/Dropbox/Research/VMAT/output/'
degreesep = 60 # How many degrees in between separating neighbor beams.
objfile = '/home/wilmer/Dropbox/IpOptSolver/TestData/HNdata/objectives/obj1.txt'
structurefile = '/home/wilmer/Dropbox/IpOptSolver/TestData/HNdata/structureInputs.txt'
algfile = '/home/wilmer/Dropbox/IpOptSolver/TestData/HNdata/algInputsWilmer.txt'
mm3voxels = rootFolder + '/Data/DataProject/HN/hn3mmvoxels.mat'
# The 1 is subtracted at read time so the user doesn't have to do it everytime
priority = [7, 24, 25, 23, 22, 21, 20, 16, 15, 14, 13, 12, 10, 11, 9, 4, 3, 1, 2, 17, 18, 19, 5, 6, 8]
priority = (np.array(priority)-1).tolist()
mylines = [line.rstrip('\n') for line in open('/home/wilmer/Dropbox/Research/VMAT/VMATwPenCode/beamAngles.txt')]

class region:
    """ Contains all information relevant to a particular region"""
    index = int()
    sizeInVoxels = int()
    indices = np.empty(1, dtype=int)
    fullIndices = np.empty(1,dtype=int)
    target = False
    # Class constructor
    def __init__(self, iind, iindi, ifullindi, itarget):
        self.index = iind
        self.sizeInVoxels = len(iindi)
        self.indices = iindi
        self.fullIndices = ifullindi
        self.target = itarget

## apertureList is a class definition of locs and angles that is always sorted.
# Its attributes are loc which is the numeric location; It has range 0 to 178 for
# the HN case; Angle is the numeric angle in degrees; It ranges from 0 to 358 degrees
# apertureList should be sorted in ascending order everytime you add a new element; User CAN make this safe assumption
class apertureList:
    ## constructor initializes empty lists
    def __init__(self):
        ## Location in index range(0,numbeams)
        self.loc = []
        ## Angles ranges from 0 to 360
        self.angle = []
    ## Insert a new angle in the list of angles to analyse.
    # Gets angle information and inserts location and angle
    # In the end it sorts the list in increasing order
    def insertAngle(self, i, aperangle):
        self.angle.append(aperangle)
        self.loc.append(i)
        # Sort the angle list in ascending order
        self.loc.sort()
        self.angle.sort()
    ## Removes the index and its corresponding angle from the list.
    # Notice that it only removes the first occurrence; but if you have done everything correctly this should never
    # be a problem
    def removeIndex(self, index):
        toremove = [i for i,x in enumerate(self.loc) if x == index]
        self.loc.pop(toremove[0]) # Notice that it removes the first entry
        self.angle.pop(toremove[0])
    ## Looks for the angle and removes the index and the angle corresponding to it from the list
    def removeAngle(self, tangl):
        toremove = [i for i,x in enumerate(self.angle) if x == tangl]
        self.loc.pop(toremove[0])
        self.angle.pop(toremove[0])
    ## Overloads parenthesis operator in order to fetch the ANGLE given an index.
    # Returns the angle at the ith location given by the index.
    # First Find the location of that index in the series of loc
    # Notice that this function overloads the parenthesis operator for elements of this class.
    def __call__(self, index):
        toreturn = [i for i,x in enumerate(self.loc) if x == index]
        return(self.angle[toreturn[0]])
    ## Returns the length of this instantiation without the need to pass parameters.
    def len(self):
        return(len(self.loc))
    ## Returns True if the list is empty; otherwise returns False.
    def isEmpty(self):
        if 0 == len(self.loc):
            return(True)
        else:
            return(False)

## This defines the global VMAT class that contains most of the VMAT data to be used in the implementation
# Most of the values were defined as static attributes and only one instantiation at a time is possible. But this should not
# be a problem. The file also contains functions to be used when you call the optimizer.
class vmat_class:
    ## number of beamlets
    numX = 0
    ## number of voxels in the small voxel space
    numvoxels = int()
    ## number of structures/regions
    numstructs = 0
    ## number of organs at risk
    numoars = 0
    ## num of targets
    numtargets = 0
    ## num of beams
    numbeams = 0
    ## num of nonzeros in Dij matrix
    totaldijs = 0
    ## objectiveValue of the final function
    objectiveValue = float("inf")
    ## number of beamlets per beam
    beamletsPerBeam = []
    ## number of nonzeroes in Dij per beam
    dijsPerBeam = []
    ## non-overlapping mask value per voxel
    maskValue = []
    ## complete mask value per voxel ( A voxel may cover more than one structure = OAR's + T's)
    fullMaskValue = []
    ## index values of structures in region list (should be 0,1,etc)
    regionIndices = []
    ## region indices of target structures (from region vector)
    targets = []
    ## region indices of oars
    oars = []
    ## vector of regions (holds structure information)
    regions = []
    ## vector of data input files for objectives
    objectiveInputFiles = []
    ## vector of data input files for constraints
    constraintInputFiles = []
    ## vector of data input for algorithm options
    algOptions = []
    ## Holds function data parameters from objectFunctioninput file
    functionData = []
    voxelAssignment = []
    ## List of apertures not yet selected
    notinC = apertureList()
    ## List of apertures already selected
    caligraphicC = apertureList()

    ## varios folders
    outputDirectory = ""# given by the user in the first lines of *.py
    dataDirectory = ""

    # dose variables
    currentDose = np.empty(1) # dose variable
    currentIntensities = np.empty(1)

    ## this is the intersection of all beamlets geographical locations in centimeters
    ## It is unique for each value in the x coordinate axis. Beamlet data is organized first in the X axis and then
    # moves onto the Y axis
    xinter = []
    ## Same as xinter but for y axis
    yinter = []

    ## This is a list of lists; There is one for each aperture angle and it contains the x coordinate of each of the
    # nonzero available beamlets
    xdirection = []
    ## Same as xdirection but in the y coordinate
    ydirection = []

    ## List of lists. Contains limits on the left side of the aperture
    llist = []
    ## List of lists. Contains limits on the right side of the aperture
    rlist = []

    ## Gradient in voxel dimensions This is the gradient of dF / dZ. Dimension is numvoxels
    voxelgradient = []

    ## This is the gradient of dF / dk. Dimension is num Apertures
    aperturegradient = []
    ## Contains the location of the beamlets that belong to open aperture and that have data available.
    openApertureMaps = []
    ## Contains data to create the diagonal matrices to process the gradient
    diagmakers = []
    dZdK = 0.0
    ## This vector produces the angle corresponding to a particular index
    pointtoAngle = []
    ## This list contains the Dose to Point matrices for each of the beam angles.
    Dlist = []
    ## This function returns the objective value and the gradient
    def calcDose(self):
        self.currentDose = np.zeros(self.numvoxels, dtype = float)
        # dZdK will have a dimension that is numvoxels x numbeams
        self.dZdK = np.matrix(np.zeros((self.numvoxels, self.numbeams)))
        if self.caligraphicC.len() != 0:
            for i in self.caligraphicC.loc:
                self.currentDose += DlistT[i][:,self.openApertureMaps[i]] * np.repeat(self.currentIntensities[i], len(self.openApertureMaps[i]), axis = 0)
                self.dZdK[:,i] = (DlistT[i] * sparse.diags(self.diagmakers[i], 0)).sum(axis=1)


    def calcGradientandObjValue(self):
        oDoseObj = self.currentDose - quadHelperThresh
        oDoseObjCl = (oDoseObj > 0) * oDoseObj
        oDoseObj = (oDoseObj > 0) * oDoseObj
        oDoseObj = oDoseObj * oDoseObj * quadHelperOver

        uDoseObj = quadHelperThresh - self.currentDose
        uDoseObjCl = (uDoseObj > 0) * uDoseObj
        uDoseObj = (uDoseObj > 0) * uDoseObj
        uDoseObj = uDoseObj * uDoseObj * quadHelperUnder

        self.objectiveValue = sum(oDoseObj + uDoseObj)

        oDoseObjGl = 2 * oDoseObjCl * quadHelperOver
        uDoseObjGl = 2 * uDoseObjCl * quadHelperUnder


        self.voxelgradient = 2 * (oDoseObjGl - uDoseObjGl)
        self.aperturegradient = (np.asmatrix(self.voxelgradient) * self.dZdK).transpose()

    # default constructor
    def __init__(self):
        self.numX = 0

########## END OF CLASS DECLARATION ###########################################

catemp = []
gatemp = []
for thisline in mylines:
    a, b = thisline.split('\t')
    if (int(float(a)) % 10 == 0):
        if(int(float(b)) % 10 == 0):
            catemp.append(a)
            gatemp.append(b)

# First of all make sure that I can read the data

# In the data directory with the *VOILIST.mat files, this opens up
# each structure file and reads in the structure names and sizes in
# voxels

start = time.time()
data = vmat_class()

data.outputDirectory = outputfolder # given by the user in the first lines of *.pydoc
data.dataDirectory = readfolder

# Function definitions
####################################################################

def readctvoxelinfo():
    # This function returns a dictionary with the dimension in voxel
    # units for x,y,z axis

    lines = [line.rstrip('\n') for line in open(readfolder + 'CTVOXEL_INFO.txt')]
    tempocoor = []
    for i in range(0,3):
        tempocoor.append(int(lines[i].rsplit(None, 1)[-1]))
    coordims = dict(x=tempocoor[0],y=tempocoor[1],z=tempocoor[2])
    return(coordims)
#########################################•••••••••###########################
oldfolder = os.getcwd()
os.chdir(readfolder)
allFiles = glob.glob("*VOILIST.mat")
allBeamInfos = glob.glob("*Couch0_BEAMINFO.mat")
allNames = sorted(allFiles) #Make sure it's sorted because it was not.
allBeamInfoNames = sorted(allBeamInfos)
numStructs = len(allFiles)

# This is "big voxel space" where some voxels may receive no dose or
# have no structure assigned
vdims = readctvoxelinfo()
numVoxels = vdims['x'] * vdims['y'] * vdims['z']

Vorg = []
bigZ = np.zeros(numVoxels, dtype=int)

# Vorg is a list of the structure voxels in big voxel space
for s in range(0, numStructs):
    Vorg.append(sio.loadmat(allNames[s])['v']-1) # correct 1 position mat2Py.
    bigZ[Vorg[s]] = 1.0

# nVox is "small voxel space", with only the voxels that have
# structures assigned (basically non-air/couch voxels)
nVox = sum(bigZ);

# voxelAssignment provides the mapping from small voxel space to big
# voxel space.
data.voxelAssignment = np.empty(nVox.astype(np.int64))
data.voxelAssignment[:] = np.NAN

counter = 0
for i in range(0, numVoxels):
    if(bigZ[i] > 0):
        # If big space voxel is nonzero, save to small vxl space
        data.voxelAssignment[counter] = i
        counter+=1
print('mapping from small voxel space to big voxel space done')

# originalVoxels is the mapping from big voxel space to small voxel
# space

# It is VERY important to initialize originalVoxels with NAN in this case.
# Or you can make an error since 0 is a valid position in python.
originalVoxels = np.empty(numVoxels); originalVoxels[:] = np.NAN
for i in range(0, nVox.astype(np.int64)):
    originalVoxels[data.voxelAssignment[i].astype(np.int64)] = i

## Read in structures . CHANGE THIS. Reading from txt file != good!!
lines = [myline.split('\t') for myline in [line.rstrip('\n') for line in open(structurefile)]]
## Collapse the above expression to a flat list
invec = [item for sublist in lines for item in sublist]
## Assignation of different values
data.numstructs = int(invec[2])
data.numtargets = int(invec[3])
data.numoars = int(invec[4])
# Structure map OARs vs. TARGETs
data.regionIndices = invec[5:(5+data.numstructs)]
data.targets = invec[(5+data.numstructs):(5+2*data.numstructs)]
data.oars = invec[(5+2*data.numstructs):(5+3*(data.numstructs))]
print('Finished reading structures')

maskValueFull = np.zeros(nVox.astype(np.int64))
maskValueSingle = np.zeros(nVox.astype(np.int64))
# this priority is the order of priority for assigning a single structure per
# voxel (from least to most important)

for i in range(0, numStructs):
    s = priority[i]
    # generates mask values (the integer that we decompose to get structure
    # assignment). for single it just overrides with the more important
    # structure
    maskValueFull[originalVoxels[Vorg[s]].astype(int)] = maskValueFull[originalVoxels[Vorg[s]].astype(int)]+2**(s)
    maskValueSingle[originalVoxels[Vorg[s]].astype(int)] = 2**(s)

print('masking value single from ' + str(min(maskValueSingle)) + ' to ' + str(max(maskValueSingle)))

# Reverse the list for the full mask value. norepeat contains all original values
# and values will be removed as they get assigned. This is to achieve precedence
# TROY!. My regions are not organized alphabetically but in inverse order of
# priority. So they won't match unless you look for the right one.
priority.reverse()
norepeat = np.unique(originalVoxels[np.invert(np.isnan(originalVoxels))])
for s in priority:
    # initialize regions
    istarget = str(s) in data.targets
    tempindicesfull = originalVoxels[Vorg[s]].astype(int) # In small voxels space
    tempindices = np.intersect1d(tempindicesfull, norepeat)
    print("initialize region " + str(s) + ', full indices: ' + str(len(tempindicesfull)) + ', and single indices: ' + str(len(tempindices)))
    data.regions.append(region(s, tempindices, tempindicesfull, istarget))
    # update the norepeat vector by removing the newly assigned indices
    norepeat = np.setdiff1d(norepeat, tempindices)

print('finished assigning voxels to regions. Region objects read')

# Read in mask values into structure data
data.maskValue = maskValueSingle
data.fullMaskValue = maskValueFull
print('Masking has been calculated')

gastart = 0 ;
gaend = 356;
if WholeCircle:
    gastep = 2;
else:
    gastep = 20;
data.pointtoAngle = range(gastart, gaend, gastep)
ga=[];
ca=[];

## Treatment of BEAMINFO data
os.chdir(readfolderD)
for g in range(gastart, gaend, gastep):
    fname = 'Gantry' + str(g) + '_Couch' + str(0) + '_D.mat'
    bletfname = readfolder + 'Gantry' + str(g) + '_Couch' + str(0) + '_BEAMINFO.mat'
    if os.path.isfile(fname) and os.path.isfile(bletfname):
        ga.append(g)
        ca.append(0)

print('There is enough data for ' + str(len(ga)) + ' beam angles\n')

# build new sparse matrices

# This code translates the sparse dose matrices from big voxel space to
# small voxel space and writes it out to a binary file to be used in the
# optimization
nBPB = np.zeros(len(ga))
nDIJSPB = np.zeros(len(ga))

###############################################################################
## Beginning of Troy's cpp code (interpreted, not copied)
## A comment
## This comes from first two lines in doseInputs txt file (troy's version)
data.numvoxels = nVox
data.numbeams = len(ga)
## Allocate memory
data.beamletsPerBeam = np.empty(data.numbeams, dtype=int)
data.dijsPerBeam = np.empty(data.numbeams, dtype=int)
data.xdirection = []
data.ydirection = []
beamletCounter = np.zeros(data.numbeams + 1)

for i in range(0, data.numbeams):
    bletfname = readfolder + 'Gantry' + str(ga[i]) + '_Couch' + str(0) + '_BEAMINFO.mat'
    # Get beamlet information
    binfoholder = sio.loadmat(bletfname)

    # Get dose information as in the cpp file
    data.beamletsPerBeam[i] = int(binfoholder['numBeamlets'])
    data.dijsPerBeam[i] =  int(binfoholder['numberNonZerosDij'])
    data.xdirection.append(binfoholder['x'][0])
    data.ydirection.append(binfoholder['y'][0])
    if 0 == i:
        data.xinter = data.xdirection[0]
        data.yinter = data.ydirection[0]
    else:
        data.xinter = np.intersect1d(data.xinter, data.xdirection[i])
        data.yinter = np.intersect1d(data.yinter, data.ydirection[i])
    data.openApertureMaps.append([]) #Just start an empty map of apertures
    data.diagmakers.append([])
## After reading the beaminfo information. Read CUT the data.

N = len(data.yinter) #N will be related to the Y axis.
M = len(data.xinter) #M will be related to the X axis.

###################################################
## Initial intensities are allocated a value of zero.
data.currentIntensities = np.zeros(data.numbeams, dtype = float)

# Generating dose matrix dimensions
data.numX = sum(data.beamletsPerBeam)
data.totaldijs = sum(data.dijsPerBeam)
# Allocate structure for full Dmat file
data.Dmat = sparse.csr_matrix((data.numX, data.numvoxels), dtype=float)

# Work with the D matrices for each beam angle
overallDijsCounter = 0
data.Dlist = [None] * data.numbeams
DlistT = [None] * data.numbeams
def readDmatrix(i):
    fname = 'Gantry' + str(ga[i]) + '_Couch' + str(0) + '_D.mat'
    print('Reading matrix from gantry & couch angle: ' + fname)
    # extract voxel, beamlet indices and dose values
    D = sio.loadmat(fname)['D']
    # write out bixel sorted binary file
    [b,j,d] = sparse.find(D)
    newb = originalVoxels[b]
    # write out voxel sorted binary file
    [jt,bt,dt] = sparse.find(D.transpose())
    newbt = originalVoxels[bt]
    Dlittle = sparse.csr_matrix((dt, (jt, newbt)), shape = (data.numX, data.numvoxels), dtype=float)
    # For each matrix D, store its values in a list
    return(i, Dlittle)

# Read the data in parallel
if __name__ == '__main__':
    pool = Pool(processes=8)              # process per MP
    Allmats = pool.map(readDmatrix, range(0, data.numbeams))

# Assign data
for objResult in Allmats:
    print('assign' + str(objResult[0]) + 'in memory')
    data.Dlist[objResult[0]] = objResult[1]

print('Finished reading D matrices')

for i in range(0, data.numbeams):
    # ininter will contain the beamlet directions that belong in the intersection of all apertures
    ininter = []
    for j in range(0, len(data.xdirection[i])):
        if (data.xdirection[i][j] in data.xinter and data.ydirection[i][j] in data.yinter):
            ininter.append(j)

    # Once I have ininter I will cut all the elements that are
    data.xdirection[i] = data.xdirection[i][ininter]
    data.ydirection[i] = data.ydirection[i][ininter]
    print(type(data.Dlist[i]))
    data.Dlist[i] = data.Dlist[i][ininter,:]
    DlistT[i] = data.Dlist[i].transpose()
    data.beamletsPerBeam[i] = len(ininter)
    beamletCounter[i+1] = beamletCounter[i] + data.beamletsPerBeam[i]

data.numX = sum(data.beamletsPerBeam)

#### MATRIX CUT DONE Here all matrices are working with the same limits

## Read in the objective file:
lines = [myline.split('\t') for myline in [line.rstrip('\n') for line in open(objfile)]]
## Collapse the above expression to a flat list
data.functionData = [item for sublist in lines for item in sublist]
data.objectiveInputFiles = objfile
print("Finished reading objective file:\n" + objfile)

## Read in the constraint file:
#####NOTHING TO DO #############

# Reading algorithm Settings
data.algOptions = [myline.split('\t') for myline in [line.rstrip('\n') for line in open(algfile)]]
print("Finished reading algorithm inputs file:\n" + algfile)

# resize dose and beamlet vectors
data.currentDose = np.zeros(data.numvoxels)
####################################
### FINISHED READING EVERYTHING ####
####################################

## Work with function data.
data.functionData = np.array([float(i) for i in data.functionData[3:len(data.functionData)]]).reshape(3,data.numstructs)
# I have to reorder the right region since my order is not alphabetical
data.functionData = data.functionData[:,priority]
functionData = data.functionData
for s in range(0, data.numstructs):
    if(data.regions[s].sizeInVoxels > 0):
        functionData[1,s] = functionData[1,s] * 1 / data.regions[s].sizeInVoxels
        functionData[2,s] = functionData[2,s] * 1 / data.regions[s].sizeInVoxels

# initialize helper variables
quadHelperThresh = np.zeros(data.numvoxels)
quadHelperOver = np.zeros(data.numvoxels)
quadHelperUnder = np.zeros(data.numvoxels)
quadHelperAlphaBetas = np.zeros(data.numvoxels)
uDose = np.zeros(data.numvoxels)
oDose = np.zeros(data.numvoxels)

# build for each voxel
for s in range(0, data.numstructs):
    for j in range(0, data.regions[s].sizeInVoxels):
        quadHelperThresh[int(data.regions[s].indices[j])] = functionData[0][s]
        quadHelperOver[int(data.regions[s].indices[j])] = functionData[1][s]
        quadHelperUnder[int(data.regions[s].indices[j])] = functionData[2][s]


def calcObjGrad(x, user_data = None):
    data.currentIntensities = x
    data.calcDose()
    data.calcGradientandObjValue()
    return(data.objectiveValue, data.aperturegradient)

## Find geographical location of the ith row in aperture index given by index.
# Input:    i:     Row
#           index: Index of this aperture
# Output:   validbeamlets ONLY contains those beamlet INDICES for which we have available data in this beam angle
#           validbeamletspecialrange is the same as validbeamlets but appending the endpoints
def fvalidbeamlets(i, index):
    geolocX = data.xinter[i] # geolocx in centimeteres. This is coordinate x of beamlet location.
    # Find all possible locations of beamlets in this row according to geographical location
    indys = np.where(geolocX == data.xdirection[index])
    geolocYs = data.ydirection[index][indys] # In centimeters. This is coordinate y of all beamlets with x coordinate == geolocX
    # Notice that geolocYs ONLY contains those beamlets that are available. As opposed to yinter which contains all.
    validbeamletlogic = np.in1d(data.yinter, geolocYs)
    # validbeamlets ONLY contains those beamlets for which we have available data in this beam angle in index coordinates
    validbeamlets = np.array(range(0, len(data.yinter)))[validbeamletlogic]
    validbeamletspecialrange = np.append(np.append(min(validbeamlets) - 1, validbeamlets), max(validbeamlets) + 1)
    # That last line appends the endpoints.
    return(validbeamlets, validbeamletspecialrange)

def PPsubroutine(C, C2, C3, b, angdistancem, angdistancep, vmax, speedlim, predec, succ, N, M, thisApertureIndex):
    # C, C2, C3 are constants in the penalization function
    # angdistancem = $\delta_{c^-c}$
    # angdistancep = $\delta_{cc^+}$
    # vmax = maximum leaf speed
    # speedlim = s
    # predec = predecesor index, either an index or an empty list
    # succ = succesor index, either an index or an empty list
    # lcm = vector of left limits in the previous aperture
    # lcp = vector of left limits in the next aperture
    # rcm = vector of right limits in the previous aperture
    # rcp = vector of right limits in the previous aperture
    # N = Number of beamlets per row
    # M = Number of rows in an aperture
    # thisApertureIndex = index location in the set of apertures that I have saved.
    posBeginningOfRow = 0
    D = data.Dlist[thisApertureIndex]
    # vmaxm and vmaxp describe the speeds that are possible for the leaves from the predecessor and to the successor
    vmaxm = vmax
    vmaxp = vmax
    # Arranging the predecessors and the succesors.
    #Predecessor left and right indices
    if type(predec) is list:
        lcm = [-1] * M
        rcm = [N] * M
        # If there is no predecessor is as if the pred. speed was infinite
        vmaxm = float("inf")
    else:
        lcm = data.llist[predec]
        rcm = data.rlist[predec]

    #Succesors left and right indices
    if type(succ) is list:
        lcp = [-1] * M
        rcp = [N] * M
        # If there is no successor is as if the succ. speed was infinite.
        vmaxp = float("inf")
    else:
        lcp = data.llist[succ]
        rcp = data.rlist[succ]

    validbeamlets, validbeamletspecialrange = fvalidbeamlets(0, thisApertureIndex)
    # First handle the calculations for the first row
    beamGrad = D * data.voxelgradient
    # Keep the location of the most leaf

    nodesinpreviouslevel = 0
    oldflag = 0
    posBeginningOfRow = 0
    thisnode = 0
    # Max beamlets per row
    bpr = 50
    networkNodesNumber = bpr * bpr + M * bpr * bpr + bpr * bpr # An overestimate of the network nodes in this network
    # Initialization of network vectors. This used to be a list before
    lnetwork = np.zeros(networkNodesNumber, dtype = np.int) #left limit vector
    rnetwork = np.zeros(networkNodesNumber, dtype = np.int) #right limit vector
    mnetwork = np.ones(networkNodesNumber, dtype = np.int) #Only to save some time in the first loop
    wnetwork = np.zeros(networkNodesNumber, dtype = np.float) # Weight Vector
    dadnetwork = np.zeros(networkNodesNumber, dtype = np.int) # Dad Vector. Where Dad is the combination of (l,r) in previous row
    # Work on the first row perimeter and area values
    leftrange = range(math.ceil(max(-1, lcm[0] - vmaxm * angdistancem/speedlim, lcp[0] - vmaxp * angdistancep / speedlim)), 1 + math.floor(min(N - 1, lcm[0] + vmaxm * angdistancem / speedlim, lcp[0] + vmaxp * angdistancep / speedlim)))
    # Check if unfeasible. If it is then assign one value but tell the result to the person running this

    if 0 == len(leftrange):
        leftrange = range(leftrange.start, leftrange.start+1)
        sys.exit('constraint leftrange at level ' + str(m) + ' aperture ' + str(thisApertureIndex) + ' could not be met')
    for l in leftrange:
        rightrange = range(math.ceil(max(l + 1, rcm[0] - vmaxm * angdistancem/speedlim, rcp[0] - vmaxp * angdistancep / speedlim)), 1 + math.floor(min(N, rcm[0] + vmaxm * angdistancem / speedlim, rcp[0] + vmaxp * angdistancep / speedlim)))
        if 0 == len(rightrange):
            rightrange = range(rightrange.start, leftrange.start+1)
            sys.exit('constraint rightrange at level ' + str(m) + ' aperture ' + str(thisApertureIndex) + ' could not be met')
        for r in rightrange:
            thisnode = thisnode + 1
            nodesinpreviouslevel = nodesinpreviouslevel + 1
            # First I have to make sure to add the beamlets that I am interested in
            if(l + 1 < r): # prints r numbers starting from l + 1. So range(3,4) = 3
                # Dose = -sum( D[[i for i in range(l+1, r)],:] * data.voxelgradient)
                possiblebeamletsthisrow = np.intersect1d(range(l+1,r), validbeamlets) - min(validbeamlets)
                if (len(possiblebeamletsthisrow) > 0):
                    Dose = -beamGrad[ possiblebeamletsthisrow ].sum()
                    weight = C * ( C2 * (r - l) - C3 * b * (r - l)) - Dose + 10E-10 * (r-l) # The last term in order to prefer apertures opening in the center
                else:
                    weight = 0.0
            else:
                weight = 0.0
            # Create node (1,l,r) in array of existing nodes and update the counter
            # Replace the following expression
            # networkNodes.append([1, l, r, weight, 0])
            lnetwork[thisnode] = l
            rnetwork[thisnode] = r
            wnetwork[thisnode] = weight
            # dadnetwork and mnetwork don't need to be changed here for obvious reasons
    posBeginningOfRow = posBeginningOfRow + nodesinpreviouslevel
    leftmostleaf = len(validbeamlets) - 1 # Position in python position(-1) of the leftmost leaf
    # Then handle the calculations for the m rows. Nodes that are neither source nor sink.
    for m in range(1,M):
        # Get the beamlets that are valid in this row in particular (all others are still valid but are zero)
        validbeamlets, validbeamletspecialrange = fvalidbeamlets(m, thisApertureIndex)
        oldflag = nodesinpreviouslevel
        nodesinpreviouslevel = 0
        # And now process normally checking against valid beamlets
        leftrange = range(math.ceil(max(-1, lcm[m] - vmaxm * angdistancem/speedlim, lcp[m] - vmaxp * angdistancep / speedlim)), 1 + math.floor(min(N - 1, lcm[m] + vmaxm * angdistancem / speedlim, lcp[m] + vmaxp * angdistancep / speedlim)))
        # Check if unfeasible. If it is then assign one value but tell the result to the person running this
        if 0 == len(leftrange):
            leftrange = range(leftrange.start, leftrange.start+1)
            sys.exit('constraint leftrange at level ' + str(m) + ' aperture ' + str(thisApertureIndex) + ' could not be met')

        for l in leftrange:
            rightrange = range(math.ceil(max(l + 1, rcm[m] - vmaxm * angdistancem/speedlim, rcp[m] - vmaxp * angdistancep / speedlim)), 1 + math.floor(min(N, rcm[m] + vmaxm * angdistancem / speedlim, rcp[m] + vmaxp * angdistancep / speedlim)))
            if 0 == len(rightrange):
                rightrange = range(rightrange.start, leftrange.start+1)
                sys.exit('constraint rightrange at level ' + str(m) + ' aperture ' + str(thisApertureIndex) + ' could not be met')

            for r in rightrange:
                nodesinpreviouslevel = nodesinpreviouslevel + 1
                thisnode = thisnode + 1
                # Create node (m, l, r) and update the level counter
                lnetwork[thisnode] = l
                rnetwork[thisnode] = r
                mnetwork[thisnode] = m
                wnetwork[thisnode] = np.inf
                # Select only those beamlets that are possible in between the (l,r) limits.
                possiblebeamletsthisrow = np.intersect1d(range(l + 1, r), validbeamlets) + leftmostleaf - min(validbeamlets)

                if(len(possiblebeamletsthisrow) > 0):
                    Dose = -beamGrad[possiblebeamletsthisrow].sum()
                    C3simplifier = C3 * b * (r - l)
                else:
                    Dose = 0.0
                    C3simplifier = 0.0
                lambdaletter = np.absolute(lnetwork[(posBeginningOfRow - oldflag): posBeginningOfRow] - l) + np.absolute(rnetwork[(posBeginningOfRow - oldflag): posBeginningOfRow] - r) - 2 * np.maximum(0, lnetwork[(posBeginningOfRow - oldflag): posBeginningOfRow] - r) - 2 * np.maximum(0, l - np.absolute(rnetwork[(posBeginningOfRow - oldflag): posBeginningOfRow]))
                weight = C * (C2 * lambdaletter - C3simplifier) - Dose  + 10E-10 * (r-l) # The last term in order to prefer apertures opening in the center
                # Add the weights that were just calculated
                newweights = wnetwork[(posBeginningOfRow - oldflag): posBeginningOfRow] + weight
                # Find the minimum and its position in the vector.
                minloc = np.argmin(newweights)
                wnetwork[thisnode] = newweights[minloc]
                dadnetwork[thisnode] = minloc + posBeginningOfRow - oldflag + 1

        posBeginningOfRow = nodesinpreviouslevel + posBeginningOfRow # This is the total number of network nodes
        # Keep the location of the leftmost leaf
        leftmostleaf = len(validbeamlets) + leftmostleaf
    # thisnode gets augmented only 1 because only the sink node will be added
    thisnode = thisnode + 1
    for mynode in (range(posBeginningOfRow - nodesinpreviouslevel + 1, posBeginningOfRow)):
        weight = C * ( C2 * (rnetwork[mynode] - lnetwork[mynode] ))
        if(wnetwork[mynode] + weight <= wnetwork[thisnode]):
            wnetwork[thisnode] = wnetwork[mynode] + weight
            dadnetwork[thisnode] = mynode
            p = wnetwork[thisnode]
    thenode = thisnode # WILMER take a look at this
    l = []
    r = []
    while(1):
        # Find the predecessor data
        l.append(lnetwork[thenode])
        r.append(rnetwork[thenode])
        thenode = dadnetwork[thenode]
        if(0 == thenode): # If at the origin then break
            break
    l.reverse()
    r.reverse()
    #Pop the last elements because this is the direction of nonexistent sink field
    l.pop(); r.pop()
    return(p, l, r)

def parallelizationPricingProblem(i, C, C2, C3, b, vmax, speedlim, N, M):
    thisApertureIndex = i

    print("analysing available aperture" , thisApertureIndex)
    # Find the succesor and predecessor of this particular element
    try:
        #This could be done with angles instead of indices (reconsider this at some point)
        succs = [i for i in data.caligraphicC.loc if i > thisApertureIndex]
    except:
        succs = []
    try:
        predecs = [i for i in data.caligraphicC.loc if i < thisApertureIndex]
    except:
        predecs = []

    # If there are no predecessors or succesors just return an empty list. If there ARE, then return the indices
    if 0 == len(succs):
        succ = []
        angdistancep = np.inf
    else:
        succ = min(succs)
        angdistancep = data.caligraphicC(succ) - data.notinC(thisApertureIndex)
    if 0 == len(predecs):
        predec = []
        angdistancem = np.inf
    else:
        predec = max(predecs)
        angdistancem = data.notinC(thisApertureIndex) - data.caligraphicC(predec)

    # Find Numeric value of previous and next angle.
    p, l, r = PPsubroutine(C, C2, C3, b, angdistancem, angdistancep, vmax, speedlim, predec, succ, N, M, thisApertureIndex)
    return(p,l,r,thisApertureIndex)

def PricingProblem(C, C2, C3, b, vmax, speedlim, N, M):
    pstar = np.inf
    bestAperture = None
    print("Choosing one aperture amongst the ones that are available")
    # Allocate empty list with enough size for all l, r combinations
    global lall
    global rall
    global pall
    lall = [None] * data.notinC.len()
    rall = [None] * data.notinC.len()
    pall = np.array([None] * data.notinC.len())

    partialparsubpp = partial(parallelizationPricingProblem, C=C, C2=C2, C3=C3, b=b, vmax=vmax, speedlim=speedlim, N=N, M=M)
    if __name__ == '__main__':
        pool = Pool(processes=8)              # process per MP
        respool = pool.map(partialparsubpp, data.notinC.loc)
    pool.close()
    pool.join()

    pvalues = np.array([result[0] for result in respool])
    indstar = np.argmin(pvalues)
    bestgroup = respool[indstar]
    pstar = bestgroup[0]
    lallret = bestgroup[1]
    rallret = bestgroup[2]
    bestApertureIndex = bestgroup[3]
    for i in range(0, len(respool)):
        if(M != len(respool[i][1])):
            sys.exit("Length of left vector is less than 28")

    print("Best aperture was: ", bestApertureIndex)
    return(pstar, lallret, rallret, bestApertureIndex)

def solveRMC():
    ## IPOPT SOLUTION
    start = time.time()
    numbe = data.caligraphicC.len()
    nvar = numbe
    xl = np.zeros(numbe)
    xu = 2e19*np.ones(numbe)
    m = 0
    gl = np.zeros(1)
    gu = 2e19*np.ones(1)
    g_L = np.array([], dtype=float)
    g_U = np.array([], dtype=float)
    nnzj = 0
    nnzh = int(numbe * (numbe + 1) / 2)

    calcObjGrad(data.currentIntensities)
    # Create the boundaries making sure that the only free variables are the ones with perfectly defined apertures.
    boundschoice = []
    for thisindex in range(0, data.numbeams):
        if thisindex in data.caligraphicC.loc: #Only activate what is an aperture
            boundschoice.append((0, None))
        else:
            boundschoice.append((0, 0))
    res = minimize(calcObjGrad, data.currentIntensities, method='L-BFGS-B', jac = True, bounds = boundschoice, options={'ftol':1e-3, 'disp':5,'maxiter':200})

    print('Restricted Master Problem solved in ' + str(time.time() - start) + ' seconds')
    return(res)

# The next function prints DVH values
def printresults(iterationNumber, myfolder):
    numzvectors = 1
    maskValueFull = np.array([int(i) for i in data.fullMaskValue])
    print('Starting to Print Results')
    for i in range(0, numzvectors):
        zvalues = data.currentDose
        maxDose = max([float(i) for i in zvalues])
        dose_resln = 0.1
        dose_ub = maxDose + 10
        bin_center = np.arange(0,dose_ub,dose_resln)
        # Generate holder matrix
        dvh_matrix = np.zeros((data.numstructs, len(bin_center)))
        lenintervalhalf = bin_center[1]/2
        # iterate through each structure
        for s in range(0,data.numstructs):
            allNames[s] = allNames[s].replace("_VOILIST.mat", "")
            doseHolder = sorted(zvalues[[i for i,v in enumerate(maskValueFull & 2**s) if v > 0]])
            if 0 == len(doseHolder):
                continue
            histHolder = []
            carryinfo = 0
            histHolder, garbage = np.histogram(doseHolder, bin_center)
            histHolder = np.append(histHolder, 0)
            histHolder = np.cumsum(histHolder)
            dvhHolder = 1-(np.matrix(histHolder)/max(histHolder))
            dvh_matrix[s,] = dvhHolder

    myfig = pylab.plot(bin_center, dvh_matrix.T, linewidth = 2.0)
    plt.grid(True)
    plt.xlabel('Dose Gray')
    plt.ylabel('Fractional Volume')
    plt.title('Iteration: ' + str(iterationNumber))
    plt.legend(allNames)
    plt.savefig(myfolder + 'DVH-at-Iteration' + str(iterationNumber) + 'greedyVMAT.png')
    plt.close()

    voitoplot = [0, 18, 23, 17, 2, 8]
    dvhsub2 = dvh_matrix[voitoplot,]
    myfig2 = pylab.plot(bin_center, dvhsub2.T, linewidth = 1.0, linestyle = '--')
    plt.grid(True)
    plt.xlabel('Dose Gray')
    plt.ylabel('Fractional Volume')
    plt.title('6 beams iteration:' + str(iterationNumber))
    #allNames.reverse()
    plt.legend([allNames[i] for i in voitoplot])
    plt.savefig(myfolder + 'DVH-at-Iteration-Subplot' + str(iterationNumber) + 'greedyVMAT.png')
    plt.close()

def colGen(C, WholeCircle, initialApertures):
    # WholeCircle: Boolean. If true the whole circle is analysed. If false, it is customized
    # initialApertures: The number of initial apertures if WholeCircle = true
    # User defined data
    C2 = 1.0
    C3 = 1.0
    vmax = 2.0 * 100
    speedlim = 3.0

    # Assign the most open apertures as initial apertures. They will not have any intensity applied to them.
    for i in range(0, data.numbeams):
        data.llist.append([-1] * len(data.xinter))
        data.rlist.append([len(data.yinter) + 1] * len(data.xinter))

    #Step 0 on Fei's paper. Set C = empty and zbar = 0. The gradient of numbeams dimensions generated here will not
    # be used, and therefore is nothing to worry about.
    # At the beginning no apertures are selected, and those who are not selected are all in notinC
    if WholeCircle:
        random.seed(13)
        global kappa
        kappa = random.sample(kappa, len(kappa))
        for j in range(0,initialApertures):
            i = kappa[0]
            data.notinC.insertAngle(i, data.pointtoAngle[i])
            kappa.pop(0)
        print('apertures initial', data.notinC)
    else:
        # Initialize kappa with the values that are given to me only
        kappa = []
        i = 0
        for j in range(gastart, gaend, gastep):
            kappa.append(i)
            i = i + 1
        random.seed(13)
        kappa = random.sample(kappa, len(kappa))
        for j in range(0, min(initialApertures, len(kappa))):
            i = kappa[0]
            data.notinC.insertAngle(i, data.pointtoAngle[i])
            kappa.pop(0)
    data.caligraphicC = apertureList()
    pstar = -np.inf
    plotcounter = 0
    optimalvalues = []
    while (pstar < 0) & (data.notinC.len() > 0):
        # Step 1 on Fei's paper. Use the information on the current treatment plan to formulate and solve an instance of the PP
        data.calcDose()
        data.calcGradientandObjValue()
        pstar, lm, rm, bestApertureIndex = PricingProblem(C, C2, C3, 0.5, vmax, speedlim, N, M)
        # Step 2. If the optimal value of the PP is nonnegative**, go to step 5. Otherwise, denote the optimal solution to the
        # PP by c and Ac and replace caligraphic C and A = Abar, k \in caligraphicC
        if pstar >= 0:
            #This choice includes the case when no aperture was selected
            break
        else:
            data.caligraphicC.insertAngle(bestApertureIndex, data.notinC(bestApertureIndex))
            data.notinC.removeIndex(bestApertureIndex)
            # Solve the instance of the RMP associated with caligraphicC and Ak = A_k^bar, k \in
            data.llist[bestApertureIndex] = lm
            data.rlist[bestApertureIndex] = rm
            # Precalculate the aperture map to save times.
            data.openApertureMaps[bestApertureIndex], data.diagmakers[bestApertureIndex] = updateOpenAperture(bestApertureIndex)
            rmpres = solveRMC()

            #epsilonflag = 0 # If some aperture was removed
            for thisindex in range(0, data.numbeams):
                if thisindex in data.caligraphicC.loc: #Only activate what is an aperture
                    if rmpres.x[thisindex] < 1e-6:
                        #epsilonflag = 1

                        # Remove from caligraphicC and add to notinC
                        data.notinC.insertAngle(thisindex, data.pointtoAngle[thisindex])
                        data.caligraphicC.removeIndex(thisindex)

            optimalvalues.append(rmpres.fun)
            plotcounter = plotcounter + 1
            # Add everything from notinC to kappa
            while(False == data.notinC.isEmpty()):
                kappa.append(data.notinC.loc[0])
                data.notinC.removeIndex(data.notinC.loc[0])

            # Choose a random set of elements in kappa
            random.seed(13)
            elemstoinclude = random.sample(kappa, min(initialApertures, len(kappa)))
            for i in elemstoinclude:
                data.notinC.insertAngle(i, data.pointtoAngle[i])
                kappa.remove(i)
            #if 31 == bestApertureIndex:
            #    print(31)
            # plotAperture(lm, rm, M, N, '/home/wilmer/Dropbox/Research/VMAT/VMATwPenCode/outputGraphics/', plotcounter, bestApertureIndex)
            printresults(plotcounter, '/home/wilmer/Dropbox/Research/VMAT/VMATwPenCode/outputGraphics/')
            #Step 5 on Fei's paper. If necessary complete the treatment plan by identifying feasible apertures at control points c
            #notinC and denote the final set of fluence rates by yk

    return(pstar)

def plotAperture(l, r, M, N, myfolder, iterationNumber, bestAperture):
    nrows, ncols = M,N
    image = np.zeros(nrows*ncols)
        # Reshape things into a 9x9 grid
    image = image.reshape((nrows, ncols))
    for i in range(0, M):
        image[i, l[i]:(r[i]-1)] = 1
    # Set up a location where to save the figure
    row_labels = range(nrows)
    col_labels = range(ncols)
    plt.matshow(image)
    plt.xticks(range(ncols), col_labels)
    plt.yticks(range(nrows), row_labels)
    #plt.savefig(myfolder + 'Aperture' + str(iterationNumber) + '-at-' + str(bestAperture * gastep) + 'degrees.png')


##This function returns the set of available AND open beamlets for the selected aperture (i).
#The idea is to have everything ready and precalculated for the evaluation of the objective function in
#calcDose
#input: i is the index number of the aperture that I'm working on
#output: openaperturenp. the set of available AND open beamlets for the selected aperture
#        diagmaker. A vector that has a 1 in each position where an openaperturebeamlet is available.
# openaperturenp is read as openapertureMaps. A member of the VMAT_CLASS.
def updateOpenAperture(i):

    leftlimits = 0
    openaperture = []
    for m in range(0, len(data.llist[i])):
        # Find geographical values of llist and rlist.
        # Find geographical location of the first row.
        validbeamlets, validbeamletspecialrange = fvalidbeamlets(m, i)
        # First index in this row
        indleft = data.llist[i][m] + 1 + leftlimits - min(validbeamlets) # I subtract min validbeamlets bec. I want to
                                                                         # find coordinates in available space
        indright = data.rlist[i][m] - 1 + leftlimits - min(validbeamlets)
        # Keep the location of the letftmost leaf
        leftlimits = leftlimits + len(validbeamlets)
        if (indleft < indright + 1): # If the leaf opening is not completely close
            for thisbeamlet in range(indleft, indright):
                openaperture.append(thisbeamlet)
    openaperturenp = np.array(openaperture, dtype=int) #Contains indices of open beamlets in the aperture
    diagmaker = np.zeros(data.Dlist[i].shape[0], dtype = float)
    diagmaker[[ij for ij in openaperturenp]] = 1.0
    return(openaperturenp, diagmaker)

print('Preparation time took: ' + str(time.time()-start) + ' seconds')

before = time.time()
# This is necessary for multiprocessing. Because if I pass into partial then I can't change
# (Try to Figure out how to get rid of this)

pstar = colGen(0, WholeCircle, 16)
after = time.time()
print("The whole process took:" , after - before)

print('The whole program took: '  + str(time.time()-start) + ' seconds to finish')

fig = plt.figure(1)
xcoor = math.ceil(math.sqrt(data.numbeams))
ycoor = math.ceil(math.sqrt(data.numbeams))
for i in range(0, data.numbeams):
    l = data.llist[i]
    r = data.rlist[i]
    fig.add_subplot(ycoor,xcoor, i + 1)
    plotAperture(l, r, M, N, '/home/wilmer/Dropbox/Research/VMAT/VMATwPenCode/outputGraphics/', i, i)

fig.savefig('/home/wilmer/Dropbox/Research/VMAT/VMATwPenCode/outputGraphics/thisplot.png')


print("You have graciously finished running this program")
