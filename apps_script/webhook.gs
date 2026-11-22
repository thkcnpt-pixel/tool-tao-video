/**
 * Google Apps Script Web App — Trạm nhận Webhook Telegram 24/7 miễn phí.
 *
 * Cách cài đặt:
 * 1. Mở Google Sheet -> Extensions (Tiện ích mở rộng) -> Apps Script.
 * 2. Dán toàn bộ file này vào Code.gs.
 * 3. Vào Project Settings (⚙️) -> Script Properties -> thêm:
 *      SHEET_ID           = ID Google Sheet (bỏ trống nếu script gắn trực tiếp trong Sheet)
 *      TELEGRAM_BOT_TOKEN = token bot
 *      TELEGRAM_CHAT_ID   = chat_id chủ kênh (chỉ người này mới bấm nút / sửa caption được)
 *      GITHUB_PAT         = Personal Access Token có quyền `repo` hoặc `workflow`
 *      GITHUB_REPO        = thkcnpt-pixel/tool-tao-video
 *      GITHUB_WORKFLOW    = publish_video.yml
 * 4. Bấm Deploy -> New deployment -> loại "Web app":
 *      Execute as: Me
 *      Who has access: Anyone
 *    Copy URL `https://script.google.com/macros/s/.../exec`.
 * 5. Trỏ webhook Telegram vào URL đó:
 *      python src/integrations/telegram_bot.py --set-webhook "URL_EXEC"
 */

var TAB = 'Schedule';
// Cột (1-based): 1:id 2:date 3:slot 4:topic 5:bg_theme 6:script_json 7:caption 8:status 9:telegram_msg_id 10:video_url_or_drive_id
var COL_ID = 1, COL_CAPTION = 7, COL_STATUS = 8, COL_MSG_ID = 9;

function getSheet_() {
  var id = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  var ss = id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName(TAB);
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
      var parts = String(cb.data || '').split(':');
      var action = parts[0], rowId = parts.slice(1).join(':');
      var r = findRow_(COL_ID, rowId);
      if (r < 0) {
        tg_('answerCallbackQuery', {callback_query_id: cb.id, text: 'Không tìm thấy dòng ' + rowId});
        return ContentService.createTextOutput('not_found');
      }
      var sh = getSheet_();
      if (action === 'APPROVE') {
        sh.getRange(r, COL_STATUS).setValue('DA_DUYET');
        var ok = dispatchPublish_(rowId);
        tg_('answerCallbackQuery', {callback_query_id: cb.id, text: 'Đã duyệt! Đang kích hoạt đăng bài...'});
        tg_('editMessageReplyMarkup', {chat_id: chatId, message_id: cb.message.message_id,
                                       reply_markup: {inline_keyboard: []}});
        tg_('sendMessage', {chat_id: chatId, reply_to_message_id: cb.message.message_id,
          text: '✅ Đã duyệt ' + rowId + (ok ? ' — đã gọi GitHub Actions publish_video.' : ' — đã lưu DA_DUYET (chưa gọi được workflow_dispatch).')});
      } else if (action === 'REJECT') {
        sh.getRange(r, COL_STATUS).setValue('DA_HUY');
        tg_('answerCallbackQuery', {callback_query_id: cb.id, text: 'Đã hủy video.'});
        tg_('editMessageReplyMarkup', {chat_id: chatId, message_id: cb.message.message_id,
                                       reply_markup: {inline_keyboard: []}});
        tg_('sendMessage', {chat_id: chatId, reply_to_message_id: cb.message.message_id,
          text: '❌ Đã hủy ' + rowId});
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
