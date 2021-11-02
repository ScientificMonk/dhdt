# function to get the basic information from the venµs imagery data

# generic libraries
import glob
import os

from xml.etree import ElementTree

import numpy as np
import pandas as pd

# geospatial libaries
from osgeo import gdal, osr

def list_central_wavelength_vn():
    wavelength = {"B1": 420, "B2" : 443, "B3" : 490, "B4" : 555, \
                  "B5": 620, "B6" : 620, "B7" : 667, "B8" : 702, \
                  "B9": 742, "B10": 782, "B11": 865, "B12": 910, \
                  }
    bandwidth = {"B1": 40, "B2" : 40, "B3" : 40, "B4" : 40, \
                 "B5": 40, "B6" : 40, "B7" : 30, "B8" : 24, \
                 "B9": 16, "B10": 16, "B11": 40, "B12": 20, \
                 }
    resolution = {"B1": 5, "B2" : 5, "B3" : 5, "B4" : 5, \
                  "B5": 5, "B6" : 5, "B7" : 5, "B8" : 5, \
                  "B9": 5, "B10": 5, "B11": 5, "B12": 5, \
                  }
    bandid = {"B1": 'B1', "B2" : 'B2', "B3" : 'B3', "B4" : 'B4', \
              "B5": 'B5', "B6" : 'B6', "B7" : 'B7', "B8" : 'B8', \
              "B9": 'B9', "B10":'B10', "B11":'B11', "B12":'B12', \
              }
    name = {"B1": 'atmospheric correction', \
            "B2" : 'aerosols', \
            "B3" : 'blue',      "B4" : 'green', \
            "B5" : 'stereo',    "B6" : 'stereo', \
            "B7" : 'red',       "B8" : 'red edge', \
            "B9": 'red edge',   "B10": 'red edge', \
            "B11":'near infrared',"B12":'water vapour',
           }    
    d = {
         "wavelength": pd.Series(wavelength),
         "bandwidth": pd.Series(bandwidth),
         "resolution": pd.Series(resolution),
         "name": pd.Series(name),
         "bandid": pd.Series(bandid)
         }
    df = pd.DataFrame(d)
    return df

def read_band_vn(path, band='00'):

    if band!='00':
        fname = os.path.join(path, '*SRE_'+band+'.tif')
    else:
        fname = path
    img = gdal.Open(glob.glob(fname)[0])
    data = np.array(img.GetRasterBand(1).ReadAsArray())
    spatialRef = img.GetProjection()
    geoTransform = img.GetGeoTransform()
    targetprj = osr.SpatialReference(wkt=img.GetProjection())
    return data, spatialRef, geoTransform, targetprj
    
# def read_sun_angles_vn(path)
def read_view_angles_vn(path):
    fname = os.path.join(path, 'DATA', 'VENUS*UII_ALL.xml')
    dom = ElementTree.parse(glob.glob(fname)[0])
    root = dom.getroot()
    
    ul_xy = np.array([float(root[0][1][2][0][2].text), \
                      float(root[0][1][2][0][3].text)])
    ur_xy = np.array([float(root[0][1][2][1][2].text), \
                      float(root[0][1][2][1][3].text)])
    lr_xy = np.array([float(root[0][1][2][2][2].text), \
                      float(root[0][1][2][2][3].text)])
    ll_xy = np.array([float(root[0][1][2][3][2].text), \
                      float(root[0][1][2][3][3].text)])
    # hard coded for detector_id="01"
    ul_za = np.array([float(root[0][2][0][1][0][0].text), \
                      float(root[0][2][0][1][0][1].text)])
    ur_za = np.array([float(root[0][2][0][1][1][0].text), \
                      float(root[0][2][0][1][1][1].text)])
    lr_za = np.array([float(root[0][2][0][1][2][0].text), \
                      float(root[0][2][0][1][2][1].text)])
    ll_za = np.array([float(root[0][2][0][1][3][0].text), \
                      float(root[0][2][0][1][3][1].text)])
        
    
    Az, Zn = 0,0
    return Az, Zn

def read_mean_sun_angles_vn(path):
    fname = os.path.join(path, 'VENUS*MTD_ALL.xml')
    dom = ElementTree.parse(glob.glob(fname)[0])
    root = dom.getroot()

    Zn = float(root[5][0][0][0].text)
    Az = float(root[5][0][0][1].text)
    return Zn, Az

def read_mean_view_angle_vn(path):
    fname = os.path.join(path, 'DATA', 'VENUS*UII_ALL.xml')
    dom = ElementTree.parse(glob.glob(fname)[0])
    root = dom.getroot()
    
    # hard coded for detector_id="01"
    Zn = float(root[0][2][0][1][4][0].text)
    Az = float(root[0][2][0][1][4][1].text)
    return Az, Zn

