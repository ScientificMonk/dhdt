import numpy as np

from osgeo import gdal, osr

from ..generic.handler_im import get_image_subset
from ..generic.mapping_tools import ref_trans, pix2map
from ..generic.mapping_io import read_geo_image
from ..input.read_sentinel2 import read_band_s2, read_sun_angles_s2
from ..input.read_rapideye import read_band_re
from .shadow_transforms import apply_shadow_transform

def create_shadow_image(dat_path, im_name, shadow_transform='ruffenacht', \
                        bbox=(0, 0, 0, 0), Shw=None):
    """
    Given a specific method, employ shadow transform
    input:   dat_path       string            directory the image is residing
             im_name        string            name of one or the multispectral image     
    output:  M              array (n x m)     shadow enhanced satellite image
    """
    bandList = get_shadow_bands(im_name) # get band numbers of the multispectral images
    (Blue, Green, Red, Nir, crs, geoTransform, targetprj) = read_shadow_bands( \
                dat_path + im_name, bandList)
        
    minI = bbox[0] 
    maxI = bbox[1] 
    minJ = bbox[2]
    maxJ = bbox[3]    
    if (minI!=0 or maxI!=0 and minI!=0 or maxI!=0):        
        # reduce image space, so it fits in memory
        Blue = get_image_subset(Blue, (minI, maxI, minJ, maxJ))
        Green = get_image_subset(Green, (minI, maxI, minJ, maxJ))
        Red = get_image_subset(Red, (minI, maxI, minJ, maxJ))
        Nir = get_image_subset(Nir, (minI, maxI, minJ, maxJ))
            
        geoTransform = ref_trans(geoTransform,minI,minJ) # create georeference for subframe
    else:
        geoTransform = geoTransform
    
    # transform to shadow image  
    RedEdge = None
    M = enhance_shadow(shadow_transform,
                       Blue, Green, Red,
                       RedEdge, Nir,
                       Shw )
    return M, geoTransform, crs

def create_caster_casted_list_from_polygons(dat_path, im_name, Rgi, 
                                            bbox=None, polygon_id=None,
                                            describtor=None):
    """
    Create a list of casted and casted coordinates, of shadow polygons that
    are occluding parts of a glacier
    
    """
    im_path = dat_path + im_name
    
    (cast, spatialRef, geoTransform, targetprj) = read_geo_image(im_path + 'labelPolygons.tif')
    img = gdal.Open(im_path + 'labelCastConn.tif')
    conn = np.array(img.GetRasterBand(1).ReadAsArray())
    
    # keep it image-based
    if polygon_id is None:
        selec = Rgi!=0
    else:
        selec = Rgi==polygon_id
    IN = np.logical_and(selec,conn<0) # are shadow edges on the glacier
    linIdx1 = np.transpose(np.array(np.where(IN)))
    
    # find the postive number (caster), that is an intersection of lists
    castPtId = conn[IN] 
    castPtId *= -1 # switch sign to get caster
    polyId = cast[IN]
    casted = np.transpose(np.vstack((castPtId,polyId))) #.tolist()
    
    IN = conn>0 # make a selection to reduce the list 
    linIdx2 = np.transpose(np.array(np.where(IN)))
    caster = conn[IN]
    polyCa = cast[IN]    
    casters = np.transpose(np.vstack((caster,polyCa))).tolist()
    
    indConn = np.zeros((casted.shape[0]))
    for x in range(casted.shape[0]):
        #idConn = np.where(np.all(casters==casted[x], axis=1))
        try:
            idConn = casters.index(casted[x].tolist())
        except ValueError:
            idConn = -1
        indConn[x] = idConn
    # transform to image coordinates
    # idMated = np.transpose(np.array(np.where(indConn!=-1)))
    OK = indConn!=-1
    idMated = indConn[OK].astype(int)
    castedIJ = linIdx1[OK,:]
    castngIJ = linIdx2[idMated,:]
    
    # transform to map coordinates  
    (castedX,castedY) = pix2map(geoTransform,castedIJ[:,0],castedIJ[:,1])
    (castngX,castngY) = pix2map(geoTransform,castngIJ[:,0],castngIJ[:,1])
    
    # get sun angles, at casting locations
    (sunZn,sunAz) = read_sun_angles_s2(im_path)
    #OBS: still in relative coordinates!!!
    if bbox is not None:
        sunZn = get_image_subset(sunZn,bbox)
        sunAz = get_image_subset(sunAz,bbox)
    sunZen = sunZn[castngIJ[:,0],castngIJ[:,1]]
    sunAzi = sunAz[castngIJ[:,0],castngIJ[:,1]]
    
    # write to file
    if polygon_id is None:
        f = open(im_path + 'conn.txt', 'w')
    else:
        f = open(im_path + 'conn-rgi' + '{:08d}'.format(polygon_id) + '.txt', 'w')  
    
    for i in range(castedX.shape[0]):
        line = '{:+8.2f}'.format(castngX[i])+' '+'{:+8.2f}'.format(castngY[i])+' '
        line = line + '{:+8.2f}'.format(castedX[i])+' '+'{:+8.2f}'.format(castedY[i])+' '
        line = line + '{:+3.4f}'.format(sunAzi[i])+' '+'{:+3.4f}'.format(sunZen[i])
        f.write(line + '\n')
    f.close()

def get_shadow_bands(satellite_name):
    """ give bandnumbers of visible bands of specific satellite

    If the instrument has a high resolution panchromatic band, 
    this is given as the fifth entry    

    Parameters
    ----------
    satellite_name : {'Sentinel-2', 'Landsat8', 'Landsat7', 'Landsat5', 
                      'RapidEye', 'PlanetScope', 'ASTER', 'Worldview3'}
        name of the satellite or instrument abreviation.

    Returns
    -------
    band_num : list, size=(1,4), integer
            
        * band_num[0] : Blue band number
        * band_num[1] : Green band number
        * band_num[2] : Red band number
        * band_num[3] : Near-infrared band number
        * band_num[4] : panchrometic band
        
    See Also
    --------
    read_shadow_bands
    """    
    satellite_name = satellite_name.lower()
    
    # compare if certain segments are present in a string
    
    if len([n for n in ['sentinel','2'] if n in satellite_name])==2 or len([n for n in ['msi'] if n in satellite_name])==1:
        band_num = [2,3,4,8] 
    elif len([n for n in ['landsat','8'] if n in satellite_name])==2 or len([n for n in ['oli'] if n in satellite_name])==1:
        band_num = [2,3,4,5,8] 
    elif len([n for n in ['landsat','7'] if n in satellite_name])==2 or len([n for n in ['etm+'] if n in satellite_name])==1:
        band_num = [1,2,3,4,8]
    elif len([n for n in ['landsat','5'] if n in satellite_name])==2 or len([n for n in ['tm','mss'] if n in satellite_name])==1:
        band_num = [1,2,3,4]
    elif len([n for n in ['rapid','eye'] if n in satellite_name])==2:
        band_num = [1,2,3,5]
    elif len([n for n in ['planet'] if n in satellite_name])==1  or len([n for n in ['dove'] if n in satellite_name])==1:
        band_num = [1,2,3,5]
    elif len([n for n in ['aster'] if n in satellite_name])==1:
        band_num = [1,1,2,3]
    elif len([n for n in ['worldview','3'] if n in satellite_name])==2:        
        band_num = [2,3,5,8]

    return band_num

def read_shadow_bands(sat_path, band_num):
    """ read the specific band numbers of the multispectral satellite images

    Parameters
    ----------
    sat_path : string
        path to imagery and file name.
    band_num : list, size=(1,4), integer
            
        * band_num[0] : Blue band number
        * band_num[1] : Green band number
        * band_num[2] : Red band number
        * band_num[3] : Near-infrared band number
        * band_num[4] : panchrometic band

    Returns
    -------
    Blue : np.array, size=(m,n), dtype=integer
        blue band of satellite image
    Green : np.array, size=(m,n), dtype=integer
        green band of satellite image
    Red : np.array, size=(m,n), dtype=integer
        red band of satellite image
    Near : np.array, size=(m,n), dtype=integer
        near-infrared band of satellite image   
    crs : string
        osr.SpatialReference in well known text
    geoTransform : tuple, size=(6,1)
        affine transformation coefficients.
    targetprj : osgeo.osr.SpatialReference() object
        coordinate reference system (CRS)
    Pan : 
        Panchromatic band
        
        * np.array, size=(m,n), integer, 
        * None if band does not exist

    """
    if len([n for n in ['S2','MSIL1C'] if n in sat_path])==2:
        # read imagery of the different bands
        (Blue, crs, geoTransform, targetprj) = read_band_s2( 
            format(band_num[0], '02d'), sat_path)
        (Green, crs, geoTransform, targetprj) = read_band_s2(
            format(band_num[1], '02d'), sat_path)
        (Red, crs, geoTransform, targetprj) = read_band_s2(
            format(band_num[2], '02d'), sat_path)
        (Near, crs, geoTransform, targetprj) = read_band_s2(
            format(band_num[3], '02d'), sat_path)
        Pan = None
    elif len([n for n in ['RapidEye','RE'] if n in sat_path])==2:
        # read single imagery and extract the different bands
        (Blue, crs, geoTransform, targetprj) = read_band_re(
            format(band_num[0], '02d'), sat_path)
        (Green, crs, geoTransform, targetprj) = read_band_re(
            format(band_num[1], '02d'), sat_path)
        (Red, crs, geoTransform, targetprj) = read_band_re(
            format(band_num[2], '02d'), sat_path)
        (Near, crs, geoTransform, targetprj) = read_band_re(
            format(band_num[3], '02d'), sat_path)
        Pan = None
        
    return Blue, Green, Red, Near, crs, geoTransform, targetprj, Pan