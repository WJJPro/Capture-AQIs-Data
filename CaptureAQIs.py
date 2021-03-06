# -*- coding: utf-8 -*-
"""
主要功能： 
从pm2.5in官网API接口获取实时气象数据，并写入pickle文件，同时记录日志文件。
1. 实时数据按月份并入历史数据的pickle文件（pandas.DataFrame格式）
2. 如需要，可用pickle_to_Excel.py脚本将pickle文件转成便于阅读的Excel文件

额外功能：
抓取失败的城市，稍后自动重新抓取

脚本执行方式：
1. 直接执行 - 抓取一次数据
2. 定时执行 - 将脚本部署在Linux云主机上，用crond设定定时执行该脚本（如每小时两次）


pm2.5in： 每小时刷新一次数据
API doc： http://www.pm25.in/api_doc


Created on Mon Jan 22 17:34:19 2018
@author: Raymond Zhang
"""

import requests
import pandas as pd
import pickle
import datetime
import traceback
from sklearn.datasets import base 
import time
import random

def check_pre_update(CityList):
      """
      将上次update的内容载入以获取：
      1. 上次更新的时间点 （判断是否取消本次更新）
      2. 上次未更新的城市 （如有，以便这次重新抓取）
      """
      try:
#            _,_,time_point,preErrorCities = pd.read_pickle('AQIsData/update.pickle')
            update = pd.read_pickle('AQIsData/update.pickle')
            time_point = update.time
            preErrorCities = update.notUpdatedCity
            
      except:
            time_point = ''
            preErrorCities = []
      return time_point,preErrorCities

            
def download_data(CityList):
      
      previous_time_point,preErrorCities = check_pre_update(CityList)
      
      # 先创建两个空的DataFrame格式的数据变量  
      # Full_stations:该城市全站点数据      City_only：该城市概况数据
      Full_stations = City_only = pd.DataFrame() 
      
      # API的访问站点
      url = 'http://www.pm25.in/api/querys/aqi_details.json'
      #url = 'http://www.pm25.in/api/querys/all_cities.json'
      token = '5j1znBVAsnSf5xQyNQyq'  # 公共token
      header = {'content-type': 'application/json; charset=utf-8',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:36.0) Gecko/20100101 Firefox/36.0',
                'Connection': 'close'}
      
      NEW_TIME_POINT = True # 超参数：这次获取的是否为新数据
      ErrorCities = [] # 由于网络等原因未能下载到数据的城市，记录之并稍后再次更新
      update_cities_for_pre = [] # 此次更新的上次未更新之城市
      ErrorCities_for_pre = []   # # 此次未能更新的上次未更新之城市

      for city in CityList:
            # 【判断时间戳及未更新城市】 如果是上次的时间戳且该城市已更新过，则跳过
            if NEW_TIME_POINT == False and city not in preErrorCities:
                  continue
            else:
                  param  = {'city':city,'token':token}
                  try:
                      r = requests.get(url, params = param,headers=header,timeout=10)
                  except Exception as e:
                        if NEW_TIME_POINT == True:
                              ErrorCities.append(city)
                        else:
                              ErrorCities_for_pre.append(city)
                        log('[Request Error]  City: [{}] is unable to download.  --> Error: {}'.format(city,e))
                        continue
                  code = r.status_code
                  #判断是否通信成功，200代表成功
                  if code == 200:
      #                  log('GET request OK： {}'.format(city))
                        content = r.json() # request模块自带函数： 将json格式转成list格式
                        if isinstance(content, dict):
                              string = 'Sorry，您这个小时内的API请求次数用完了'
                              if list(content.keys())==['error'] and content['error'].startswith(string):
                                  log('[Failed]   token of API is out of use: {}'.format(city))
                              else:
                                  log('[Failed]   Unknown response for {}'.format(city))
#                              log(city+': '+str(content))
                              return
                        elif isinstance(content, list):
                              # 获取此次更新的时间： 选择最后一条（for city），以免某些废站点的数据误导
                              time_point = content[-1]['time_point']
                              # 判断是否与上次获取数据的时间点,不同则执行此次更新
                              if time_point != previous_time_point:
                                    NEW_TIME_POINT = True
                                    city_data = pd.DataFrame(content).fillna('')
                                    Full_stations = Full_stations.append(city_data, ignore_index=True)
                                    # 从该城市全部站点中提取城市概况数据，记为City_only
                                    City_only = City_only.append(city_data.iloc[-1], ignore_index=True)
                              # 时间点相同
                              else:
                                    NEW_TIME_POINT = False
                                    # 如果没有上次未更新的城市，则取消本次更新，直接退出
                                    if len(preErrorCities) == 0:
                                          log('[Canceled] Same as the previous')
                                          return
                                    # 如有，则更新该城市的数据
                                    else:
                                          city_data = pd.DataFrame(content).fillna('')
                                          Full_stations = Full_stations.append(city_data, ignore_index=True)
                                          City_only = City_only.append(city_data.iloc[-1], ignore_index=True)
                                          if city in preErrorCities:
                                              update_cities_for_pre.append(city)

                  # 未访问成功
                  else:
                        if NEW_TIME_POINT == True:
                              ErrorCities.append(city)
                        else:
                              ErrorCities_for_pre.append(city)
                        log('[Request Error]    GET request error {}: {}'.format(code,city))

      # 更新新时间点的数据
      if NEW_TIME_POINT == True:
            if len(ErrorCities)==0:
                  infor = '[Success]  Updated all cities!       TimePoint: {}'.format(str(time_point))
            elif 0<len(ErrorCities)<len(CityList):
                  infor = '[Success]  Updated some of cities!   TimePoint: {}   --> Not updated: {}'.format(str(time_point),ErrorCities)
            elif len(ErrorCities)==len(CityList):
                  log('[Failed]   No cities are updated!')
                  return
            return [infor,[Full_stations,City_only,ErrorCities]]

      # 更新上次未更新的城市
      elif len(preErrorCities) != 0:
            if len(update_cities_for_pre) == 0:
                  log('[Failed]   No cities are updated for previous (TimePoint: {}) not-updated city(s)!'.format(previous_time_point))
                  return
            elif len(update_cities_for_pre) < len(preErrorCities):
                  infor = '[Success]  Updated: {}    Not updated: {}   TimePoint: {}'.format(update_cities_for_pre,ErrorCities_for_pre,str(time_point))
            elif len(update_cities_for_pre) == len(preErrorCities):
                  infor = '[Success]  Updated all previous not-updated cities!     TimePoint: {}   Updated: {}'.format(str(time_point),update_cities_for_pre)
            return [infor,[Full_stations,City_only,ErrorCities_for_pre]]



def update_to_pickle(data):
      Full_stations,City_only,ErrorCities = data
      # 改变列顺序，使之更易读
      columns = ['time_point','area','position_name','station_code','aqi','quality',
                 'primary_pollutant','pm2_5', 'pm2_5_24h','pm10', 'pm10_24h',
                 'co', 'co_24h', 'no2', 'no2_24h', 'o3', 'o3_24h', 
                 'o3_8h', 'o3_8h_24h','so2', 'so2_24h']
      Full_stations = Full_stations.reindex(columns=columns)
      City_only = City_only.reindex(columns=columns) 
      City_only.pop('position_name')
      City_only.pop('station_code')
      time_point = City_only.iloc[0,0]
#      time_point = City_only.ix[0,'time_point']
      
      # 保存此次update的数据
      with open('AQIsData/update.pickle', 'wb') as file:
            data = base.Bunch(full = Full_stations, 
                              city = City_only, 
                              time = time_point,
                              notUpdatedCity = ErrorCities)
            pickle.dump(data, file)
            
      # 将更新并入历史数据
      month = time_point[:7]
      his_filename = '{}.pickle'.format(month) # 按月存放数据于一文件中
      filepath = 'AQIsData/'+his_filename
      import os
      if os.path.exists(filepath):
            try:
#                  Full_his, City_his, time_his = pd.read_pickle(filepath)
                  his = pd.read_pickle(filepath)
                  Full_his = his.full  
                  City_his = his.city
                  time_his = his.time
            except Exception as e:
                  # 如无法获取该月份的历史数据，为了避免覆写历史数据的误操作，将本次更新的数据另建一pickle，以待后续手动合并
                  filename = 'not-merged-Data-{}.pickle'.format(time_point)
                  with open(r'AQIsData/'+filename, 'wb') as file:
#                        pickle.dump([Full_stations, City_only, time_point], file)
                        data = base.Bunch(full = Full_stations, 
                                          city = City_only, 
                                          time = time_point,
                                          notUpdatedCity = ErrorCities)
                        pickle.dump(data, file)
                  log('[Error]  Fail to load [{}] and unable to merge into his data. \
                                     Create an extra file:{}.  ({})'.format(his_filename,filename,e))
                  return 
      else:
            #否则新建新月份的pickle文件
            Full_his = City_his = pd.DataFrame()
            time_his = pd.Series()
            log('=======================================================================================')
            log('[New his pickle] Create {}'.format(his_filename))
      # 合并之
      Full_his = pd.concat([Full_stations, Full_his], axis=0, join='outer', ignore_index=True)
      City_his = pd.concat([City_only, City_his], axis=0, join='outer', ignore_index=True)
      time_his = pd.Series(time_point).append(time_his,ignore_index=True)
      with open(filepath, 'wb') as file:
#            pickle.dump([Full_his, City_his, time_his], file)
            data = base.Bunch(full = Full_his, 
                              city = City_his, 
                              time = time_his)
            pickle.dump(data, file)

def log(infor):
      ''' 
      该函数记录日志文件
      infor: 本次记录之内容
      旧记录在后，新纪录在前（与传统方式略有不同，以便查看最新状况） 
      '''
      
      filepath = r'AQIsData/{}.log'.format(time.strftime("%Y-%m"))
      
      # 先读入第二行后的内容
      try:
            with open(filepath, 'r') as f:
                  content = f.readlines()[2:]
      except:
            content = ''
      # 然后将本条记录插在旧记录前面，保持最新的永远在最前面
      with open(filepath, 'w') as f:
            head = '     Log Time       | Informaiton\n\n' #表头
            now = str(datetime.datetime.now())[:-7]
            update = '{} | {}\n'.format(now,infor)
            try:
                print(update)
            except Exception as e:
                print('print(update) occurs an error! --> {}'.format(e))
            f.write(head+update)   # 添加日志时间并写入
            f.writelines(content)  # 然后将之前的旧日志附在后面


def main():
      # 要抓取的城市，这里以广东九市为例
      CityList = ['guangzhou','zhaoqing','foshan','huizhou','dongguan',
                  'zhongshan','shenzhen','jiangmen','zhuhai']
      
      # 伪装： 在Linux中采用crond方式定时抓数据时，将按整分钟执行，容易被服务器reject，故延迟一随机时间
      # 直接执行该脚本则无需time.sleep()
      time.sleep(random.uniform(1, 19))
      
      data = download_data(CityList)
      
      # 如果data为空则无需update
      if data!=None:
            infor, updateData = data
            update_to_pickle(updateData)
            log(infor)


if __name__ == '__main__':      
      try:
            main()
      except Exception:
            log('[Error] \n{}'.format(traceback.format_exc()))

