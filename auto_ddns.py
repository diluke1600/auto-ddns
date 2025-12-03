#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动DDNS脚本 - 自动获取公网IP并更新到阿里云DNS
"""

import json
import os
import sys
import logging
import requests
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.acs_exception.exceptions import ClientException, ServerException
from aliyunsdkalidns.request.v20150109 import DescribeDomainRecordsRequest, UpdateDomainRecordRequest, AddDomainRecordRequest

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ddns.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class AliDNSUpdater:
    """阿里云DNS更新器"""
    
    def __init__(self, access_key_id, access_key_secret, region='cn-hangzhou'):
        """
        初始化阿里云DNS客户端
        
        Args:
            access_key_id: 阿里云AccessKey ID
            access_key_secret: 阿里云AccessKey Secret
            region: 区域，默认为杭州
        """
        self.client = AcsClient(access_key_id, access_key_secret, region)
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
    
    def get_current_ip(self):
        """
        获取当前公网IP地址
        
        Returns:
            str: 当前公网IP地址，失败返回None
        """
        ip_services = [
            'https://api.ipify.org?format=json',
            'https://api64.ipify.org?format=json',
            'https://ifconfig.me/ip',
            'https://icanhazip.com',
        ]
        
        for service in ip_services:
            try:
                if 'ipify' in service:
                    response = requests.get(service, timeout=10)
                    data = response.json()
                    ip = data.get('ip')
                else:
                    response = requests.get(service, timeout=10)
                    ip = response.text.strip()
                
                if ip and self._is_valid_ip(ip):
                    logger.info(f"成功获取IP地址: {ip} (来源: {service})")
                    return ip
            except Exception as e:
                logger.warning(f"从 {service} 获取IP失败: {e}")
                continue
        
        logger.error("所有IP服务都失败，无法获取公网IP")
        return None
    
    def _is_valid_ip(self, ip):
        """验证IP地址格式"""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False
    
    def get_domain_records(self, domain_name, rr='ai'):
        """
        获取域名记录
        
        Args:
            domain_name: 主域名，如 uih-devops.com
            rr: 子域名，如 ai，完整域名为 ai.uih-devops.com
        
        Returns:
            list: 记录列表
        """
        try:
            request = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
            request.set_DomainName(domain_name)
            request.set_RRKeyWord(rr)
            request.set_Type('A')
            
            response = self.client.do_action_with_exception(request)
            result = json.loads(response)
            
            if result.get('DomainRecords', {}).get('Record'):
                return result['DomainRecords']['Record']
            return []
        except Exception as e:
            logger.error(f"获取域名记录失败: {e}")
            return []
    
    def update_domain_record(self, record_id, rr, record_type, value, ttl=600):
        """
        更新域名记录
        
        Args:
            record_id: 记录ID
            rr: 子域名
            record_type: 记录类型，如 A
            value: 记录值，即IP地址
            ttl: TTL值，默认600秒
        
        Returns:
            bool: 是否成功
        """
        try:
            request = UpdateDomainRecordRequest.UpdateDomainRecordRequest()
            request.set_RecordId(record_id)
            request.set_RR(rr)
            request.set_Type(record_type)
            request.set_Value(value)
            request.set_TTL(ttl)
            
            response = self.client.do_action_with_exception(request)
            result = json.loads(response)
            
            if result.get('RequestId'):
                logger.info(f"成功更新DNS记录: {rr} -> {value}")
                return True
            return False
        except Exception as e:
            logger.error(f"更新DNS记录失败: {e}")
            return False
    
    def add_domain_record(self, domain_name, rr, record_type, value, ttl=600):
        """
        添加域名记录
        
        Args:
            domain_name: 主域名
            rr: 子域名
            record_type: 记录类型
            value: 记录值
            ttl: TTL值
        
        Returns:
            bool: 是否成功
        """
        try:
            request = AddDomainRecordRequest.AddDomainRecordRequest()
            request.set_DomainName(domain_name)
            request.set_RR(rr)
            request.set_Type(record_type)
            request.set_Value(value)
            request.set_TTL(ttl)
            
            response = self.client.do_action_with_exception(request)
            result = json.loads(response)
            
            if result.get('RecordId'):
                logger.info(f"成功添加DNS记录: {rr}.{domain_name} -> {value}")
                return True
            return False
        except Exception as e:
            logger.error(f"添加DNS记录失败: {e}")
            return False
    
    def update_ddns(self, full_domain):
        """
        更新DDNS记录
        
        Args:
            full_domain: 完整域名，如 ai.uih-devops.com
        
        Returns:
            bool: 是否成功
        """
        # 解析域名
        parts = full_domain.split('.')
        if len(parts) < 2:
            logger.error(f"域名格式错误: {full_domain}")
            return False
        
        rr = parts[0]  # ai
        domain_name = '.'.join(parts[1:])  # uih-devops.com
        
        logger.info(f"开始更新DDNS: {full_domain}")
        
        # 获取当前IP
        current_ip = self.get_current_ip()
        if not current_ip:
            return False
        
        # 获取现有记录
        records = self.get_domain_records(domain_name, rr)
        
        if records:
            # 如果记录已存在，检查是否需要更新
            record = records[0]
            existing_ip = record.get('Value')
            record_id = record.get('RecordId')
            
            if existing_ip == current_ip:
                logger.info(f"IP地址未变化 ({current_ip})，无需更新")
                return True
            
            logger.info(f"IP地址已变化: {existing_ip} -> {current_ip}")
            return self.update_domain_record(record_id, rr, 'A', current_ip)
        else:
            # 如果记录不存在，创建新记录
            logger.info(f"记录不存在，创建新记录: {rr}.{domain_name} -> {current_ip}")
            return self.add_domain_record(domain_name, rr, 'A', current_ip)


def load_config():
    """加载配置文件"""
    config_file = os.path.join(os.path.dirname(__file__), 'config.json')
    
    if not os.path.exists(config_file):
        logger.error(f"配置文件不存在: {config_file}")
        logger.info("请创建 config.json 文件，格式如下:")
        logger.info('''{
    "access_key_id": "your_access_key_id",
    "access_key_secret": "your_access_key_secret",
    "domain": "ai.uih-devops.com"
}''')
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}")
        return None


def main():
    """主函数"""
    config = load_config()
    if not config:
        sys.exit(1)
    
    access_key_id = config.get('access_key_id')
    access_key_secret = config.get('access_key_secret')
    domain = config.get('domain', 'ai.uih-devops.com')
    
    if not access_key_id or not access_key_secret:
        logger.error("配置文件中缺少 access_key_id 或 access_key_secret")
        sys.exit(1)
    
    updater = AliDNSUpdater(access_key_id, access_key_secret)
    
    if updater.update_ddns(domain):
        logger.info("DDNS更新成功")
        sys.exit(0)
    else:
        logger.error("DDNS更新失败")
        sys.exit(1)


if __name__ == '__main__':
    main()

