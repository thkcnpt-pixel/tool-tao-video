/**
 * Google Apps Script Web App — Trạm nhận Webhook Telegram 24/7 miễn phí (có LockService + chống duyệt trùng 100%).
 */
var DEFAULT_SHEET_ID = '1ZXl4mwJ3XWA_L428OG78LK1olhrWEpqptlwhx6CKxNo';
var TAB = 'Schedule';
// Cột (1-based): 1:id 2:date 3:slot 4:topic 5:bg_theme 6:script_json 7:caption 8:status 9:telegram_msg_id 10:video_url_or_drive_id
var COL_ID = 1, COL_CAPTION = 7, COL_STATUS = 8, COL_MSG_ID = 9;

function getSheet_() {
  var id = PropertiesService.getScriptProperties().getProperty('SHEET_ID') || DEFAULT_SHEET_ID;
  return SpreadsheetApp.openById(id).getSheetByName(TAB);
}

function findRow_(col, val) {
  var sh = getSheet_();
  var data = sh.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][col - 1]) === String(val)) return i + 1;
  }
  return -1;
}

function tg_(method, payload) {
  var token = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/' + method, {
    method: 'post', contentType: 'application/json',
    payload: JSON.stringify(payload), muteHttpExceptions: true
  });
}

function dropPendingWebhook_() {
  var p = PropertiesService.getScriptProperties();
  var token = p.getProperty('TELEGRAM_BOT_TOKEN');
  var url = ScriptApp.getService().getUrl();
  if (!token || !url) return;
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/setWebhook', {
    method: 'post', contentType: 'application/json',
    payload: JSON.stringify({url: url, drop_pending_updates: true, allowed_updates: ['message', 'callback_query']}),
    muteHttpExceptions: true
  });
}

function dispatchPublish_(rowId) {
  var p = PropertiesService.getScriptProperties();
  var pat = p.getProperty('GITHUB_PAT');
  var repo = p.getProperty('GITHUB_REPO') || 'thkcnpt-pixel/tool-tao-video';
  var wf = p.getProperty('GITHUB_WORKFLOW') || 'publish_video.yml';
  if (!pat) return false;
  var url = 'https://api.github.com/repos/' + repo + '/actions/workflows/' + wf + '/dispatches';
  var res = UrlFetchApp.fetch(url, {
    method: 'post', contentType: 'application/json',
    headers: {'Authorization': 'Bearer ' + pat, 'Accept': 'application/vnd.github+json'},
    payload: JSON.stringify({ref: 'main', inputs: {video_id: String(rowId)}}),
    muteHttpExceptions: true
  });
  return res.getResponseCode() === 204;
}

function doPost(e) {
  try {
    var update = JSON.parse(e.postData.contents);
    var allow = String(PropertiesService.getScriptProperties().getProperty('TELEGRAM_CHAT_ID') || '');

    // 1) Bấm nút [✅ Duyệt] / [❌ Hủy]
    if (update.callback_query) {
      var cb = update.callback_query;
      var chatId = String(cb.message.chat.id);
      if (allow && chatId !== allow) return ContentService.createTextOutput('forbidden');

      // Trả lời Telegram NGAY LẬP TỨC để tắt vòng xoay trên nút & ngăn Telegram retry
      tg_('answerCallbackQuery', {callback_query_id: cb.id, text: 'Đang xử lý...'});

      // Khóa đồng bộ (LockService) chống 2 request chạy song song khi bấm nhiều lần
      var lock = LockService.getScriptLock();
      if (!lock.tryLock(10000)) return ContentService.createTextOutput('busy');

      try {
        var parts = String(cb.data || '').split(':');
        var action = parts[0], rowId = parts.slice(1).join(':');
        var r = findRow_(COL_ID, rowId);
        if (r < 0) return ContentService.createTextOutput('not_found');

        var sh = getSheet_();
        var curStatus = String(sh.getRange(r, COL_STATUS).getValue() || '');

        // CHỐNG LẶP TUYỆT ĐỐI: chỉ xử lý nếu dòng đó đang ở trạng thái CHO_DUYET!
        if (curStatus !== 'CHO_DUYET') {
          tg_('editMessageReplyMarkup', {chat_id: chatId, message_id: cb.message.message_id,
                                         reply_markup: {inline_keyboard: []}});
          return ContentService.createTextOutput('already_processed');
        }

        if (action === 'APPROVE') {
          sh.getRange(r, COL_STATUS).setValue('DA_DUYET');
          SpreadsheetApp.flush(); // ghi xuống Sheet ngay trước khi gọi GitHub
          tg_('editMessageReplyMarkup', {chat_id: chatId, message_id: cb.message.message_id,
                                         reply_markup: {inline_keyboard: []}});
          var ok = dispatchPublish_(rowId);
          tg_('sendMessage', {chat_id: chatId, reply_to_message_id: cb.message.message_id,
            text: '✅ Đã duyệt ' + rowId + (ok ? ' — đã gọi GitHub Actions publish_video.' : ' — đã lưu DA_DUYET.')});
        } else if (action === 'REJECT') {
          sh.getRange(r, COL_STATUS).setValue('DA_HUY');
          SpreadsheetApp.flush();
          tg_('editMessageReplyMarkup', {chat_id: chatId, message_id: cb.message.message_id,
                                         reply_markup: {inline_keyboard: []}});
          tg_('sendMessage', {chat_id: chatId, reply_to_message_id: cb.message.message_id,
            text: '❌ Đã hủy ' + rowId});
        }
        dropPendingWebhook_();
      } finally {
        lock.releaseLock();
      }
      return ContentService.createTextOutput('ok');
    }

    // 2) Reply vào tin nhắn video để sửa caption
    if (update.message && update.message.reply_to_message && update.message.text) {
      var m = update.message;
      var mChat = String(m.chat.id);
      if (allow && mChat !== allow) return ContentService.createTextOutput('forbidden');
      var replyId = String(m.reply_to_message.message_id);
      var row = findRow_(COL_MSG_ID, replyId);
      if (row > 0) {
        getSheet_().getRange(row, COL_CAPTION).setValue(m.text.trim());
        tg_('sendMessage', {chat_id: mChat, reply_to_message_id: m.message_id,
          text: '✏️ Đã cập nhật caption mới vào Google Sheets. Bạn có thể bấm ✅ Duyệt ở tin nhắn video.'});
      }
    }
  } catch (err) {
    console.error(err);
  }
  return ContentService.createTextOutput('ok');
}

function doGet() {
  return ContentService.createTextOutput('tool-tao-video webhook alive');
}
