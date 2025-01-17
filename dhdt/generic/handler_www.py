# generic libraries
import os

import tarfile
import zipfile
import urllib.request

import ftps # for Copernicus FTP-download

# geospatial libaries
from osgeo import gdal

def get_file_from_ftps(url, user, password,
                       file_path, file_name, dump_dir=os.getcwd()):
    """ Downloads a file from a ftps-server

    Paramters
    ---------
    url : string
        server address
    user : string
        username
    password : string
        password for access
    file_path : string
        location on the server
    file_name : string
        name of the file
    dump_dir : string
        path to place the content
    """
    if dump_dir[-1]!='/':
        dump_dir += '/'
    client = ftps.FTPS('ftps://' +user+ ':' +password+ '@' +url)
    client.list()
    client.download( os.path.join(file_path, file_name),
                     os.path.join(dump_dir, file_name))
    return

def url_exist(file_url):
    """ Check if an url exist

    Parameters
    ----------
    file_url : string
        url of www location

    Returns
    -------
    verdict : dtype=boolean
        verdict if present
    """
    
    try: 
        urllib.request.urlopen(file_url).code == 200
        return True
    except:
        return False

def get_tar_file(tar_url, dump_dir=os.getcwd()):
    """ Downloads and unpacks compressed folder

    Parameters
    ----------
    tar_url : string
        url of world wide web location
    dump_dir : string
        path to place the content

    Returns
    -------
    tar_names : list
        list of strings of file names within the compressed folder
    """
    
    ftp_stream = urllib.request.urlopen(tar_url)
    tar_file = tarfile.open(fileobj=ftp_stream, mode="r|gz")
    tar_file.extractall(path=dump_dir)
    tar_names = tar_file.getnames()
    return tar_names

def get_zip_file(zip_url, dump_dir=os.getcwd()):
    """ Downloads and unpacks compressed folder

    Parameters
    ----------
    zip_url : string
        url of world wide web location
    dump_dir : string
        path to place the content

    Returns
    -------
    zip_names : list
        list of strings of file names within the compressed folder
    """
    zip_resp = urllib.request.urlopen(zip_url)
    temp_zip = open(dump_dir + 'tempfile.zip', "wb") 
    temp_zip.write(zip_resp.read())
    temp_zip.close()
    
    zf = zipfile.ZipFile(dump_dir + "tempfile.zip")
    zf.extractall(path = dump_dir)
    zf.close()    

    os.remove(dump_dir + 'tempfile.zip')

def bulk_download_and_mosaic(url_list, dem_path, sat_tile, bbox, crs, new_res=10):

    for i in range(len(url_list)):
        gran_url = url_list[i]
        gran_url_new = change_url_resolution(gran_url,new_res)
        
        # download and integrate DEM data into tile
        print('starting download of DEM tile')
        if url_exist(gran_url_new):
            tar_names = get_tar_file(gran_url_new, dem_path)
        else:
            tar_names = get_tar_file(gran_url, dem_path)
        print('finished download of DEM tile')
            
        # load data, interpolate into grid
        dem_name = [s for s in tar_names if 'dem.tif' in s]
        if i ==0:
            dem_new_name = sat_tile + '_DEM.tif'
        else:
            dem_new_name = dem_name[0][:-4]+'_utm.tif'
        
        ds = gdal.Warp(os.path.join(dem_path, dem_new_name), 
                       os.path.join(dem_path, dem_name[0]), 
                       dstSRS=crs,
                       outputBounds=(bbox[0], bbox[2], bbox[1], bbox[3]),
                       xRes=new_res, yRes=new_res,
                       outputType=gdal.GDT_Float64)
        ds = None
        
        if i>0: # mosaic tiles togehter
            merge_command = ['python', 'gdal_merge.py', 
                             '-o', os.path.join(dem_path, sat_tile + '_DEM.tif'), 
                             os.path.join(dem_path, sat_tile + '_DEM.tif'), 
                             os.path.join(dem_path, dem_new_name)]
            my_env = os.environ['CONDA_DEFAULT_ENV']
            os.system('conda run -n ' + my_env + ' '+
                      ' '.join(merge_command[1:]))
            os.remove(os.path.join(dem_path,dem_new_name))
            
        for fn in tar_names:
            os.remove(os.path.join(dem_path,fn))

def change_url_resolution(url_string,new_res):
    """ the file name can have the spatail resolution within, this function
    replaces this string

    Paramters
    ---------
    url_string : string
        url of world wide web location
    new_res : integer
        new resolution (10, 32, ...)

    Returns
    -------
    url_string : string
        url of new world wide web location
    """
    
    # get resolution
    props = url_string.split('_')
    for i in range(1,len(props)):
        if props[i][-1] == 'm':
            old_res = props[i]
            props[i] = str(new_res)+'m'
    
    if (old_res=='2m') & (new_res==10):
        # the files are subdivided in quads
        props = props[:-4]+props[-2:]
    
    url_string_2 = '_'.join(props)
    
    folders = url_string_2.split('/')
    for i in range(len(folders)):
        print
        if folders[i] == old_res:
            folders[i] = str(new_res)+'m'
    
    gran_url_new = '/'.join(folders)
    return gran_url_new

def reduce_duplicate_urls(url_list):
    """ because the shapefiles are in 2 meter, the tiles are 4 fold, therfore
    make a selection, to bypass duplicates

    Parameters
    ----------
    url_list : list
          list of strings with url's of www locations

    Returns
    -------
    url_list : list
        reduced list of strings with url's of www location
    """
    tiles = ()
    for i in url_list: 
        tiles += (i.split('/')[-2],)
    uni_set = set(tiles)
    ids = []
    for i in range(len(uni_set)):
        idx = tiles.index(uni_set.pop())
        ids.append(idx)
    url_list = [url_list[i] for i in ids]    
#    print('reduced to '+str(len(url_list))+ ' elevation chips')
    return url_list
