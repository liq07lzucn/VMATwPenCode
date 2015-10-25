
#!/usr/bin/python

import glob, os
import pyipopt
import numpy as np
import scipy.io as sio
from scipy import sparse
from scipy.optimize import minimize

# First of all make sure that I can read the data

# In the data directory with the *VOILIST.mat files, this opens up
# each structure file and reads in the structure names and sizes in
# voxels

readfolder = '/home/wilmer/Documents/Troy_BU/Data/DataProject/HN/'
readfolderD = readfolder + 'Dij/'
outputfolder = '/home/wilmer/Dropbox/Research/VMAT/output/'
degreesep = 60 # How many degrees in between separating neighbor beams.
objfile = '/home/wilmer/Dropbox/IpOptSolver/TestData/HNdata/objectives/obj1.txt'
structurefile = '/home/wilmer/Dropbox/IpOptSolver/TestData/HNdata/structureInputs.txt'
algfile = '/home/wilmer/Dropbox/IpOptSolver/TestData/HNdata/algInputsWilmer.txt'
# The 1 is subtracted at read time so the user doesn't have to do it everytime
priority = [7, 24, 25, 23, 22, 21, 20, 16, 15, 14, 13, 12, 10, 11, 9, 4, 3, 1, 2, 17, 18, 19, 5, 6, 8]
priority = (np.array(priority)-1).tolist()

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

class imrt_class:
    # constants particular to the problem
    numX = 0 # num beamlets
    numvoxels = int() #num voxels (small voxel space)
    numstructs = 0 # num of structures/regions
    numoars = 0 # num of organs at risk
    numtargets = 0 # num of targets
    numbeams = 0 # num of beams
    totaldijs = 0 # num of nonzeros in Dij matrix
    nnz_jac_g = 0

    # vectors
    beamNumPerBeam = [] # beam index per beam (for reading in individual beams)
    beamletsPerBeam = [] # number of beamlets per beam 
    dijsPerBeam = [] # number of nonzeroes in Dij per beam
    maskValue = [] #non-overlapping mask value per voxel
    fullMaskValue = [] # complete mask value per voxel
    regionIndices = [] # index values of structures in region list (should be 0,1,etc)
    targets = [] # region indices of structures (from region vector)
    oars = [] # region indices of oars
    regions = [] # vector of regions (holds structure information)
    objectiveInputFiles = [] # vector of data input files for objectives
    constraintInputFiles = [] # vector of data input files for constraints
    algOptions = [] # vector of data input for algorithm options
    functionData = []
    voxelAssignment = []

    # big D matrix
    Dmat = sparse.csr_matrix((1,1), dtype=float) # sparse Dij matrix
    
    # varios folders
    outputDirectory = outputfolder # given by the user in the first lines of *.py
    dataDirectory = readfolder

    # dose variables
    currentDose = [] # dose variable
    currentIntensities = []

    # data class function
    def calcDose(self, newIntensities):
        self.currentIntensities = newIntensities
        self.currentDose = self.Dmat.transpose() * newIntensities
    
    # default constructor
    def __init__(self):
        self.numX = 0

########## END OF CLASS DECLARATION ###########################################
data = imrt_class()

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
####################################################################
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

## Read in structures WILMER. CHANGE THIS. Reading from txt file != good!!
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

# CAREFUL!!!! masking value gets indices that agree with Troy's matlab implemen
# tation. My reasoning is that I want to be compatible with his code down the
# road. minimum maskin value will be 1 (one).
for i in range(0, numStructs):
    s = priority[i]
    # generates mask values (the integer that we decompose to get structure
    # assignment). for single it just overrides with the more important
    # structure
    maskValueFull[originalVoxels[Vorg[s]].astype(int)] = maskValueFull[originalVoxels[Vorg[s]].astype(int)]+2**(s)
    maskValueSingle[originalVoxels[Vorg[s]].astype(int)] = 2**(s)
    # print('s: ' + str(s) + ', mValue:' + str(maskValueFull[111001]))

print('masking value single from ' + str(min(maskValueSingle)) + ' to ' + str(max(maskValueSingle)))

# Reverse the list for the full mask value. norepeat contains all original values
# and values will be removed as they get assigned. This is to achieve precedence
# TROY!. My regions are not organized alphabetically but in inverse order of
# priority. So they won't match unless you look for the right one.
priority.reverse()
norepeat = unique(originalVoxels[np.invert(np.isnan(originalVoxels))])
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
gastep = degreesep;
castart = 0;
caend = 0;
castep = 0;
ga=[];
ca=[];

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

# nBPB is the  number of beamlets per beam
nBPB = np.zeros(len(ga))
# nDIJSPB is the number of nonzeros in the Dmatrix for each beam
nDIJSPB = np.zeros(len(ga))

###############################################################################
## Beginning of Troy's cpp code (interpreted, not copied)

## This comes from first two lines in doseInputs txt file (troy's version)
data.numvoxels = nVox
data.numbeams = len(ga)
## Allocate memory
data.beamNumPerBeam = np.empty(data.numbeams, dtype=int)
data.beamletsPerBeam = np.empty(data.numbeams, dtype=int)
data.dijsPerBeam = np.empty(data.numbeams, dtype=int)
beamletCounter = np.zeros(data.numbeams + 1)

for i in range(0, data.numbeams):
    bletfname = readfolder + 'Gantry' + str(ga[i]) + '_Couch' + str(0) + '_BEAMINFO.mat'
    # Get beamlet information
    binfoholder = sio.loadmat(bletfname)

    # Get dose information as in the cpp file
    data.beamNumPerBeam[i] = 10 * int(i) # WILMER. Find out why!!!
    data.beamletsPerBeam[i] = int(binfoholder['numBeamlets'])
    data.dijsPerBeam[i] =  int(binfoholder['numberNonZerosDij'])
    beamletCounter[i+1] = beamletCounter[i] + data.beamletsPerBeam[i]
    
# Generating dose matrix dimensions
data.numX = sum(data.beamletsPerBeam)
data.totaldijs = sum(data.dijsPerBeam)
# Allocate structure for full Dmat file
data.Dmat = sparse.csr_matrix((data.numX, data.numvoxels), dtype=float)

# Work with the D matrices for each beam angle
overallDijsCounter = 0
for i in range(0, data.numbeams):
    fname = 'Gantry' + str(ga[i]) + '_Couch' + str(0) + '_D.mat'
    print('Processing matrix from gantry & couch angle: ' + fname)
    # extract voxel, beamlet indices and dose values
    D = sio.loadmat(fname)['D']
    # write out bixel sorted binary file
    [b,j,d] = sparse.find(D)
    newb = originalVoxels[b]
    data.nnz_jac_g += len(b)
    nBPB[i] = max(j)
    nDIJSPB[i] = len(d)

    # write out voxel sorted binary file
    [jt,bt,dt] = sparse.find(D.transpose())
    newbt = originalVoxels[bt]
    # Notice here that python is smart enough to subtract 1 from matlab's mat
    # files (where the index goes). This was confirmed by Wilmer on 10/19/2015
    tempsparse=sparse.csr_matrix((dt,(jt + beamletCounter[i], newbt)),
                                 shape=(data.numX, data.numvoxels), dtype=float)
    data.Dmat = data.Dmat + tempsparse

    ## Can I erase the below part?
    beamlog = np.ones(len(ga))
    nBeams = len(ga)
    nBeamlets = np.zeros(nBeams)
    rowCumSum = []
print('Finished reading D matrices')

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
data.functionData = np.array([double(i) for i in data.functionData[3:len(data.functionData)]]).reshape(3,data.numstructs)
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

def evaluateFunction(x, user_data= None):
    data.calcDose(x)
    oDoseObj = data.currentDose - quadHelperThresh
    oDoseObj = (oDoseObj > 0) * oDoseObj
    oDoseObj = oDoseObj * oDoseObj * quadHelperOver
    uDoseObj = quadHelperThresh - data.currentDose
    uDoseObj = (uDoseObj > 0) * uDoseObj
    uDoseObj = uDoseObj * uDoseObj * quadHelperUnder
    objectiveValue = sum(oDoseObj + uDoseObj)
    return(objectiveValue)

def evaluateGradient(x, user_data= None):
    data.calcDose(x)
    oDoseObj = data.currentDose - quadHelperThresh
    uDoseObj = quadHelperThresh - data.currentDose
    oDoseObjCl = (oDoseObj > 0) * oDoseObj
    uDoseObjCl = (uDoseObj > 0) * uDoseObj
    oDoseObjGl = oDoseObjCl * quadHelperOver
    uDoseObjGl = uDoseObjCl * quadHelperUnder
    my2gradient = data.Dmat * 2 * (oDoseObjGl - uDoseObjGl)
    return(my2gradient)

def calcObjGrad(x):
    data.calcDose(x)
    oDoseObj = data.currentDose - quadHelperThresh
    oDoseObjCl = (oDoseObj > 0) * oDoseObj
    oDoseObjGl = oDoseObjCl * oDoseObjCl * quadHelperOver
    uDoseObj = quadHelperThresh - data.currentDose
    uDoseObjCl = (uDoseObj > 0) * uDoseObj
    uDoseObjGl = uDoseObjCl * uDoseObjCl * quadHelperUnder
    objectiveValue = sum(oDoseObjGl + uDoseObjGl)
    oDoseObjGl = oDoseObjCl * quadHelperOver
    uDoseObjGl = uDoseObjCl * quadHelperUnder
    mygradient = data.Dmat * 2 * (oDoseObjGl - uDoseObjGl)
    return(objectiveValue, mygradient)

def evaluateHessian(x, lagrange, obj_factor, flag, user_data = None):
    if flag:
        # Build helper array
        data.calcDose(x)
        values = np.zeros(int(data.numX * (data.numX + 1) / 2), float_)
        #hessian = sparse.csr_matrix((data.numX, data.numX))
        quadHelperAlphaBetas = (data.currentDose < quadHelperThresh) * 2 * quadHelperUnder
        quadHelperAlphaBetas += (data.currentDose >= quadHelperThresh) * 2 * quadHelperOver
        # generate Hessian using matrix multiplication
        abDmat = obj_factor * data.Dmat *sparse.diags(quadHelperAlphaBetas, 0)* data.Dmat.transpose()
        
        #[i,j,d] = sparse.find(abDmat)
        hessian = abDmat.todense()
        idx = 0
        for i in range(0, data.numX):
            for j in range(0,i):
                values[idx] = hessian[i,j]
                idx += 1
    else:
        # Build helper array
        data.calcDose(x)
        values = np.zeros(int(data.numX * (data.numX + 1) / 2), float_)
        #hessian = sparse.csr_matrix((data.numX, data.numX))
        quadHelperAlphaBetas = (data.currentDose < quadHelperThresh) * 2 * quadHelperUnder
        quadHelperAlphaBetas += (data.currentDose >= quadHelperThresh) * 2 * quadHelperOver
        # generate Hessian using matrix multiplication
        abDmat = obj_factor * data.Dmat *sparse.diags(quadHelperAlphaBetas, 0)* data.Dmat.transpose()
        
        #[i,j,d] = sparse.find(abDmat)
        hessian = abDmat.todense()
        idx = 0
        for i in range(0, data.numX):
            for j in range(0,i):
                values[idx] = hessian[i,j]
                idx += 1
    return(values)


def eval_g(x, user_data= None):
           return array([], float_)

def eval_jac_g(x, flag, user_data = None):
    if flag:
        return ([ ], [])
    else:
        return array([ ])

## IPOPT SOLUTION

data.currentIntensities = np.zeros(data.numX)
nvar = data.numX
xl = np.zeros(data.numX)
xu = 2e19*np.ones(data.numX)
m = 0
gl = np.zeros(1)
gu = 2e19*np.ones(1)
g_L = numpy.array([], dtype=float)
g_U = numpy.array([], dtype=float)
nnzj = 0
nnzh = int(data.numX * (data.numX + 1) / 2)

nlp = pyipopt.create(nvar, xl, xu, m, g_L, g_U, nnzj, nnzh, evaluateFunction, evaluateGradient, eval_g, eval_jac_g, evaluateHessian)
data.currentIntensities = np.zeros(data.numX)
nlp.num_option('tol', 1e-3)
nlp.str_option('hessian_approximation', 'limited-memory')
nlp.str_option('mu_strategy', 'adaptive')
nlp.str_option('mu_oracle', 'probing')
nlp.str_option('linear_solver', 'ma97')
nlp.num_option('acceptable_tol', 1e-1)
x, zl, zu, constraint_multipliers, obj, status = nlp.solve(data.currentIntensities)

# PYTHON scipy.optimize solution

# find initial location
# data.currentIntensities = np.zeros(data.numX)
# res = minimize(calcObjGrad, data.currentIntensities,method='L-BFGS-B', jac = True, bounds=[(0, None) for i in range(0, len(data.currentIntensities))], options={'ftol':1e-6,'disp':5})


