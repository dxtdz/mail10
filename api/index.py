from flask import Flask, request, jsonify, session, redirect, url_for, flash, make_response
import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime, timedelta
import hashlib
import secrets
from functools import wraps
from user_agents import parse
import sys
import tempfile

# Thêm thư mục gốc vào path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import app từ file chính
from app import app as flask_app

# Vercel handler
def handler(request):
    return flask_app(request)
