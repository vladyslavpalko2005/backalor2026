from __future__ import annotations
import secrets
import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token


def exchange_code(settings,code,verifier,nonce):
    response=requests.post('https://oauth2.googleapis.com/token', data={
        'code':code, 'client_id':settings.google_client_id,'client_secret':settings.google_client_secret,
        'redirect_uri':settings.redirect_uri,'grant_type':'authorization_code','code_verifier':verifier},timeout=20)
    response.raise_for_status()
    token=response.json().get('id_token')
    if not token:raise ValueError('Google did not return an ID token')
    claims=id_token.verify_oauth2_token(token,Request(),settings.google_client_id)
    if not secrets.compare_digest(str(claims.get('nonce','')),nonce):raise ValueError('Invalid nonce')
    if claims.get('iss') not in ('accounts.google.com','https://accounts.google.com'):raise ValueError('Invalid issuer')
    if claims.get('email_verified') is not True or not claims.get('sub') or not claims.get('email'):
        raise ValueError('Verified Google identity is required')
    if claims.get('azp') and claims['azp'] != settings.google_client_id:raise ValueError('Invalid authorized party')
    return {'sub':str(claims['sub']),'email':str(claims['email']), 'name':str(claims.get('name',claims['email']))}
