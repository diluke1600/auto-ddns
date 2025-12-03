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
from datetime import datetime
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


class FeishuNotifier:
    """飞书Webhook通知器"""
    
    def __init__(self, webhook_url):
        """
        初始化飞书通知器
        
        Args:
            webhook_url: 飞书Webhook URL
        """
        self.webhook_url = webhook_url
    
    def send_card_notification(self, domain, ip, status, message, old_ip=None):
        """
        发送飞书卡片通知
        
        Args:
            domain: 域名
            ip: 当前IP地址（可能为None）
            status: 状态（success/updated/no_change/failed）
            message: 消息内容
            old_ip: 旧IP地址（如果有变化）
        
        Returns:
            bool: 是否发送成功
        """
        if not self.webhook_url:
            return False
        
        # 根据状态设置颜色和标题
        status_config = {
            'success': {'color': 'green', 'title': '✅ DDNS更新成功', 'icon': '✅'},
            'updated': {'color': 'blue', 'title': '🔄 DDNS已更新', 'icon': '🔄'},
            'no_change': {'color': 'grey', 'title': 'ℹ️ DDNS检查完成', 'icon': 'ℹ️'},
            'failed': {'color': 'red', 'title': '❌ DDNS更新失败', 'icon': '❌'}
        }
        
        config = status_config.get(status, status_config['failed'])
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 处理IP显示
        ip_display = ip if ip else "获取失败"
        
        # 构建卡片消息
        card_content = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": config['title']
                    },
                    "template": config['color']
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**域名：**\n{domain}"
                                }
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**当前IP：**\n`{ip_display}`"
                                }
                            }
                        ]
                    }
                ]
            }
        }
        
        # 如果有旧IP且IP发生变化，显示IP变化信息
        if old_ip and ip and old_ip != ip:
            card_content["card"]["elements"].append({
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**旧IP：**\n`{old_ip}`"
                        }
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**新IP：**\n`{ip}`"
                        }
                    }
                ]
            })
        
        # 添加状态消息
        card_content["card"]["elements"].append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**状态：** {message}"
            }
        })
        
        # 添加时间戳
        card_content["card"]["elements"].append({
            "tag": "hr"
        })
        card_content["card"]["elements"].append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"更新时间: {current_time}"
                }
            ]
        })
        
        try:
            response = requests.post(
                self.webhook_url,
                json=card_content,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                logger.info("飞书通知发送成功")
                return True
            else:
                logger.warning(f"飞书通知发送失败: {result.get('msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"发送飞书通知时出错: {e}")
            return False


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
            dict: 包含更新结果的字典
                {
                    'success': bool,  # 是否成功
                    'domain': str,    # 域名
                    'ip': str,        # 当前IP
                    'old_ip': str,    # 旧IP（如果有）
                    'status': str,    # 状态：success/updated/no_change/failed
                    'message': str    # 状态消息
                }
        """
        # 解析域名
        parts = full_domain.split('.')
        if len(parts) < 2:
            error_msg = f"域名格式错误: {full_domain}"
            logger.error(error_msg)
            return {
                'success': False,
                'domain': full_domain,
                'ip': None,
                'old_ip': None,
                'status': 'failed',
                'message': error_msg
            }
        
        rr = parts[0]  # ai
        domain_name = '.'.join(parts[1:])  # uih-devops.com
        
        logger.info(f"开始更新DDNS: {full_domain}")
        
        # 获取当前IP
        current_ip = self.get_current_ip()
        if not current_ip:
            error_msg = "无法获取当前公网IP地址"
            logger.error(error_msg)
            return {
                'success': False,
                'domain': full_domain,
                'ip': None,
                'old_ip': None,
                'status': 'failed',
                'message': error_msg
            }
        
        # 获取现有记录
        records = self.get_domain_records(domain_name, rr)
        
        if records:
            # 如果记录已存在，检查是否需要更新
            record = records[0]
            existing_ip = record.get('Value')
            record_id = record.get('RecordId')
            
            if existing_ip == current_ip:
                message = f"IP地址未变化 ({current_ip})，无需更新"
                logger.info(message)
                return {
                    'success': True,
                    'domain': full_domain,
                    'ip': current_ip,
                    'old_ip': existing_ip,
                    'status': 'no_change',
                    'message': message
                }
            
            logger.info(f"IP地址已变化: {existing_ip} -> {current_ip}")
            success = self.update_domain_record(record_id, rr, 'A', current_ip)
            
            if success:
                return {
                    'success': True,
                    'domain': full_domain,
                    'ip': current_ip,
                    'old_ip': existing_ip,
                    'status': 'updated',
                    'message': f"DNS记录已更新: {existing_ip} -> {current_ip}"
                }
            else:
                return {
                    'success': False,
                    'domain': full_domain,
                    'ip': current_ip,
                    'old_ip': existing_ip,
                    'status': 'failed',
                    'message': f"DNS记录更新失败"
                }
        else:
            # 如果记录不存在，创建新记录
            logger.info(f"记录不存在，创建新记录: {rr}.{domain_name} -> {current_ip}")
            success = self.add_domain_record(domain_name, rr, 'A', current_ip)
            
            if success:
                return {
                    'success': True,
                    'domain': full_domain,
                    'ip': current_ip,
                    'old_ip': None,
                    'status': 'success',
                    'message': f"DNS记录创建成功: {full_domain} -> {current_ip}"
                }
            else:
                return {
                    'success': False,
                    'domain': full_domain,
                    'ip': current_ip,
                    'old_ip': None,
                    'status': 'failed',
                    'message': f"DNS记录创建失败"
                }


def load_config():
    """加载配置文件"""
    config_file = os.path.join(os.path.dirname(__file__), 'config.json')
    
    if not os.path.exists(config_file):
        logger.error(f"配置文件不存在: {config_file}")
        logger.info("请创建 config.json 文件，格式如下:")
        logger.info('''{
    "access_key_id": "your_access_key_id",
    "access_key_secret": "your_access_key_secret",
    "domain": "ai.uih-devops.com",
    "feishu_webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
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
    feishu_webhook_url = config.get('feishu_webhook_url', '')
    
    if not access_key_id or not access_key_secret:
        logger.error("配置文件中缺少 access_key_id 或 access_key_secret")
        sys.exit(1)
    
    updater = AliDNSUpdater(access_key_id, access_key_secret)
    
    # 执行DDNS更新
    result = updater.update_ddns(domain)
    
    # 发送飞书通知（无论是否更新都通知）
    if feishu_webhook_url:
        notifier = FeishuNotifier(feishu_webhook_url)
        notifier.send_card_notification(
            domain=result['domain'],
            ip=result['ip'],
            status=result['status'],
            message=result['message'],
            old_ip=result.get('old_ip')
        )
    else:
        logger.info("未配置飞书Webhook URL，跳过通知")
    
    # 根据结果设置退出码
    if result['success']:
        logger.info(f"DDNS操作完成: {result['message']}")
        sys.exit(0)
    else:
        logger.error(f"DDNS操作失败: {result['message']}")
        sys.exit(1)


if __name__ == '__main__':
    main()

