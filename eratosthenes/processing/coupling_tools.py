import math

import numpy as np

from sklearn.neighbors import NearestNeighbors

from eratosthenes.generic.mapping_tools import map2pix, pix2map, rotMat 
from eratosthenes.processing.matching_tools import normalized_cross_corr

def pair_images(conn1, conn2, thres=20):
    """
    Find the closest correspnding points in two lists, 
    within a certain bound (given by thres)
    """
    nbrs = NearestNeighbors(n_neighbors=1, algorithm='auto').fit(conn1[:,0:2])
    distances, indices = nbrs.kneighbors(conn2[:,0:2])
    IN = distances<thres
    idxConn = np.transpose(np.vstack((np.where(IN)[0], indices[IN])))
    return idxConn



# create file with approx shadow cast locations

# refine by matching, and include correlation score

def match_shadow_casts(M1, M2, geoTransform1, geoTransform2,
                       xy1, xy2, temp_radius=7, search_radius=22):
    """
    
    """
    i1, j1 = map2pix(geoTransform1, xy1[:,0], xy1[:,1])
    i2, j2 = map2pix(geoTransform2, xy2[:,0], xy2[:,1])
    
    i1 = np.round(i1).astype(np.int64)
    j1 = np.round(j1).astype(np.int64)
    i2 = np.round(i2).astype(np.int64)
    j2 = np.round(j2).astype(np.int64)
    
    ij2_corr = np.zeros((i1.shape[0],2)).astype(np.float64)
    xy2_corr = np.zeros((i1.shape[0],2)).astype(np.float64)
    corr_score = np.zeros((i1.shape[0],1)).astype(np.float16)
    for counter in range(len(i1)):
        M1_sub = M1[i1[counter] - temp_radius:i1[counter] + temp_radius + 1,
                j1[counter] - temp_radius:j1[counter] + temp_radius + 1]
        M2_sub = M2[i2[counter] - search_radius:i2[counter] + search_radius + 1,
                j2[counter] - search_radius:j2[counter] + search_radius + 1]
        # matching
        di,dj,corr = normalized_cross_corr(M1_sub, M2_sub)
        corr_score[counter] = corr
        ij2_corr[counter,0] = i2[counter] + di - (search_radius - temp_radius)
        ij2_corr[counter,1] = j2[counter] + dj - (search_radius - temp_radius)
    xy2_corr[:,0], xy2_corr[:,1] = pix2map(geoTransform1, ij2_corr[:,0], ij2_corr[:,1])
    
    return xy2_corr, corr_score


# establish dH between locations

# 

def angles2unit(azimuth):
    """
    Transforms arguments in degrees to unit vector, in planar coordinates
    input:
    azimuth argument with clockwise angle direction
    output:
    x mapping coordinate, in Eastwards direction
    y mapping coordinate, in Nordwards direction
    
    """
    x = np.sin(np.radians(azimuth))
    y = np.cos(np.radians(azimuth))
    
    xy = np.stack((x,y)).T
    
    return xy
    
def get_intersection(xy_1, xy_2, xy_3, xy_4):
    """
    given two points per line, estimate the intersection
    """
    
    x_1 = xy_1[:,0]
    y_1 = xy_1[:,1]
    x_2 = xy_2[:,0]
    y_2 = xy_2[:,1]
    x_3 = xy_3[:,0]
    y_3 = xy_3[:,1]
    x_4 = xy_4[:,0]
    y_4 = xy_4[:,1]    
    
    numer_1 = x_1*y_2 - y_1*x_2
    numer_2 = x_3*y_4 - y_3*x_4
    dx_12 = x_1 - x_2
    dx_34 = x_3 - x_4
    dy_12 = y_1 - y_2
    dy_34 = y_3 - y_4
    denom = (dx_12*dy_34 - dy_12*dx_34)
    
    x = ( numer_1 * dx_34 - dx_12 * numer_2) / denom
    y = ( numer_1 * dy_34 - dy_12 * numer_2) / denom 
    
    xy = np.stack((x,y)).T
    return xy

def get_elevation_difference(sun_1, sun_2, xy_1, xy_2, xy_t):
    """
    input:   azimuth_t      array (2 x 1)     argument in degrees of the 
                                              occluder
             zenit_t        array (n x m)     zenith angle in degrees of the 
                                              sun at the location of the 
                                              occluder
             x_c            array (2 x 1)     map coordinates of casted shadow
             y_c            array (2 x 1)     map coordinates of casted shadow
    output:  dh             array (n x m)     elevation difference estimate
             xy_t           array (n x m)     caster location
    """
    # dxy_1 = angles2unit(sun_1[:,0])*1e3
    # dxy_2 = angles2unit(sun_2[:,0])*1e3

    # # get the location of the casting point
    # xy_t = get_intersection(xy_1, xy_1 + dxy_1, 
    #                              xy_2, xy_2 + dxy_2)
       
    # get planar distance between 
    dist_1 = np.sqrt((xy_1[:,0]-xy_t[:,0])**2 + (xy_1[:,1]-xy_t[:,1])**2)
    dist_2 = np.sqrt((xy_2[:,0]-xy_t[:,0])**2 + (xy_2[:,1]-xy_t[:,1])**2)
    
    # get elevation difference 
    dh = np.tan(np.radians(sun_1[:,1]))*dist_1 - \
        np.tan(np.radians(sun_2[:,1]))*dist_2
        
    return dh #, xy_t

def transform_to_elevation_difference(sun_1, sun_2, xy_1, xy_2):
    """    
    input:   azimuth_t      array (2 x 1)     argument in degrees of the 
                                              occluder
             zenit_t        array (n x m)     zenith angle in degrees of the 
                                              sun at the location of the 
                                              occluder
             x_c            array (2 x 1)     map coordinates of casted shadow
             y_c            array (2 x 1)     map coordinates of casted shadow
    output:  dh             array (n x m)     elevation difference
    """    
    
    # translate coordinate system to the middle
    xy_mean = np.stack((xy_1[:,0]/2+xy_2[:,0]/2,xy_1[:,1]/2+xy_2[:,1]/2)).T
    xy_1_tilde = xy_1 - xy_mean
    xy_2_tilde = xy_2 - xy_mean
    del xy_mean
    
    # rotate coordinate system towards mean argument
    azi_mean = np.arctan2(0.5* (np.sin(np.deg2rad(sun_1[:,0])) + 
                                np.sin(np.deg2rad(sun_2[:,0]))) , 
                          0.5* (np.cos(np.deg2rad(sun_2[:,0])) + 
                                np.cos(np.deg2rad(sun_2[:,0])) )
                          ) # in radians
    xy_1_tilde = np.stack((+ np.cos(azi_mean) * xy_1_tilde[:,0]
                           - np.sin(azi_mean) * xy_1_tilde[:,1], 
                           + np.sin(azi_mean) * xy_1_tilde[:,0]
                           + np.cos(azi_mean) * xy_1_tilde[:,1])
                          ).T
    xy_2_tilde = np.stack((+ np.cos(azi_mean) * xy_2_tilde[:,0]
                           - np.sin(azi_mean) * xy_2_tilde[:,1], 
                           + np.sin(azi_mean) * xy_2_tilde[:,0]
                           + np.cos(azi_mean) * xy_2_tilde[:,1])
                          ).T
    del axi_mean
    
    # extract length
    dxy_tilde = xy_1_tilde - xy_2_tilde
    dzenit = sun_1[:,1] - sun_2[:,1]

    # translate to elevation difference
    
    
    
    return dh
    
    