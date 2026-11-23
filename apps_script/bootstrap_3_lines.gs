var U='https://raw.githubusercontent.com/thkcnpt-pixel/tool-tao-video/main/apps_script/webhook.gs';
function doPost(e){return eval(UrlFetchApp.fetch(U).getContentText()) && doPost(e);}
function doGet(e){return eval(UrlFetchApp.fetch(U).getContentText()) && doGet(e);}
