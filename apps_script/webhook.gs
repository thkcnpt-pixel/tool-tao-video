/**
 * Google Apps Script Web App — Trạm điều khiển Telegram 24/7 miễn phí.
 * Hỗ trợ:
 *   - Nút [✅ Duyệt] / [🔄 Tạo lại] / [❌ Hủy]
 *   - Reply vào video để sửa caption
 *   - Menu lệnh tự động hiện khi gõ dấu /:
 *       /tao <chủ đề>   -> tạo ngay video mới theo chủ đề bạn gõ (bỏ trống chủ đề thì lấy từ lịch CHO_TAO)
 *       /sang, /trua, /toi -> tạo ngay 1 video cho đúng ca Sáng / Trưa / Tối
 *       /lich           -> xem thống kê số bài chờ tạo / chờ duyệt / đã đăng + link mở Google Sheet
 *       /help           -> bảng hướng dẫn chi tiết toàn bộ tính năng để không bao giờ quên
 */
var DEFAULT_SHEET_ID = '1ZXl4mwJ3XWA_L428OG78LK1olhrWEpqptlwhx6CKxNo';
var TAB = 'Schedule';
var COL_ID = 1, COL_TOPIC = 4, COL_CAPTION = 7, COL_STATUS = 8, COL_MSG_ID = 9;

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
  var token = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
  var url = ScriptApp.getService().getUrl();
  if (!token || !url) return;
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/setWebhook', {
    method: 'post', contentType: 'application/json',
    payload: JSON.stringify({url: url, drop_pending_updates: true, allowed_updates: ['message', 'callback_query']}),
    muteHttpExceptions: true
  });
}

function dispatchWorkflow_(wfName, inputs) {
  var p = PropertiesService.getScriptProperties();
  var pat = p.getProperty('GITHUB_PAT');
  var repo = p.getProperty('GITHUB_REPO') || 'thkcnpt-pixel/tool-tao-video';
  if (!pat) return false;
  var url = 'https://api.github.com/repos/' + repo + '/actions/workflows/' + wfName + '/dispatches';
  var res = UrlFetchApp.fetch(url, {
    method: 'post', contentType: 'application/json',
    headers: {'Authorization': 'Bearer ' + pat, 'Accept': 'application/vnd.github+json'},
    payload: JSON.stringify({ref: 'main', inputs: inputs || {}}),
    muteHttpExceptions: true
  });
  return res.getResponseCode() === 204;
}

var HELP_TEXT =
  '📖 HƯỚNG DẪN SỬ DỤNG TOOL TẠO VIDEO 9:16\n\n' +
  '1️⃣ CÁC LỆNH GÕ NHANH (chỉ cần gõ dấu / là hiện menu):\n' +
  '• /tao — Dựng ngay 1 video tiếp theo trong lịch\n' +
  '• /tao <chủ đề> — Dựng ngay video theo chủ đề bạn gõ\n' +
  '  (VD: /tao 3 mẹo dùng Gemini Pro làm báo cáo)\n' +
  '• /sang — Dựng ngay 1 video cho Ca Sáng (05:00)\n' +
  '• /trua — Dựng ngay 1 video cho Ca Trưa (11:30)\n' +
  '• /toi — Dựng ngay 1 video cho Ca Tối (18:00)\n' +
  '• /lich — Xem số bài Chờ tạo, Chờ duyệt, Đã đăng & link Google Sheet\n' +
  '• /help — Xem lại bảng hướng dẫn này\n\n' +
  '2️⃣ CÁCH DUYỆT & SỬA VIDEO KHI BOT GỬI VỀ:\n' +
  '• ✏️ Sửa Caption: Chạm giữ vào tin nhắn video -> chọn Trả lời (Reply) -> gõ caption mới.\n' +
  '• 🔄 Tạo lại: Bấm nút [🔄 Tạo lại] để AI viết kịch bản mới và dựng lại video khác.\n' +
  '• ✅ Duyệt: Bấm nút [✅ Duyệt] -> Tự động đăng lên YouTube Shorts (tự lên lịch giờ vàng hoặc bật Public ngay) + trả Bản Final sạch về đây để bạn đăng TikTok.\n' +
  '• ❌ Hủy: Bỏ qua video đó.\n\n' +
  '3️⃣ LỊCH CHẠY TỰ ĐỘNG HÀNG NGÀY (GIỜ VN):\n' +
  '• Ca Sáng: 04:00 dựng -> 05:00 lên sóng\n' +
  '• Ca Trưa: 10:30 dựng -> 11:30 lên sóng\n' +
  '• Ca Tối: 17:00 dựng -> 18:00 lên sóng\n' +
  '🔗 Google Sheet: https://docs.google.com/spreadsheets/d/' + DEFAULT_SHEET_ID + '/edit';

function doPost(e) {
  try {
    var update = JSON.parse(e.postData.contents);
    var allow = String(PropertiesService.getScriptProperties().getProperty('TELEGRAM_CHAT_ID') || '');

    // 1) Bấm nút [✅ Duyệt] / [🔄 Tạo lại] / [❌ Hủy]
    if (update.callback_query) {
      var cb = update.callback_query;
      var chatId = String(cb.message.chat.id);
      if (allow && chatId !== allow) return ContentService.createTextOutput('forbidden');

      tg_('answerCallbackQuery', {callback_query_id: cb.id, text: 'Đang xử lý...'});

      var lock = LockService.getScriptLock();
      if (!lock.tryLock(10000)) return ContentService.createTextOutput('busy');
      try {
        var parts = String(cb.data || '').split(':');
        var action = parts[0], rowId = parts.slice(1).join(':');
        var r = findRow_(COL_ID, rowId);
        if (r < 0) return ContentService.createTextOutput('not_found');

        var sh = getSheet_();
        var curStatus = String(sh.getRange(r, COL_STATUS).getValue() || '');
        if (curStatus !== 'CHO_DUYET') {
          tg_('editMessageReplyMarkup', {chat_id: chatId, message_id: cb.message.message_id,
                                         reply_markup: {inline_keyboard: []}});
          dropPendingWebhook_();
          return ContentService.createTextOutput('already_processed');
        }

        if (action === 'APPROVE') {
          sh.getRange(r, COL_STATUS).setValue('DA_DUYET');
          SpreadsheetApp.flush();
          tg_('editMessageReplyMarkup', {chat_id: chatId, message_id: cb.message.message_id,
                                         reply_markup: {inline_keyboard: []}});
          var ok = dispatchWorkflow_('publish_video.yml', {video_id: String(rowId)});
          tg_('sendMessage', {chat_id: chatId, reply_to_message_id: cb.message.message_id,
            text: '✅ Đã duyệt ' + rowId + (ok ? ' — đang đăng YouTube Shorts & xuất bản Final...' : ' — đã lưu DA_DUYET.')});
        } else if (action === 'REGEN') {
          sh.getRange(r, COL_STATUS).setValue('CHO_TAO');
          SpreadsheetApp.flush();
          tg_('editMessageReplyMarkup', {chat_id: chatId, message_id: cb.message.message_id,
                                         reply_markup: {inline_keyboard: []}});
          var okR = dispatchWorkflow_('produce_video.yml', {video_id: String(rowId)});
          tg_('sendMessage', {chat_id: chatId, reply_to_message_id: cb.message.message_id,
            text: '🔄 Đang dựng lại kịch bản & video mới cho ' + rowId + ' (~2-3 phút)...'});
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

    // 2) Tin nhắn văn bản: Lệnh /help, /start, /tao, /sang, /trua, /toi, /lich hoặc Reply sửa caption
    if (update.message && update.message.text) {
      var m = update.message;
      var mChat = String(m.chat.id);
      if (allow && mChat !== allow) return ContentService.createTextOutput('forbidden');
      var txt = m.text.trim();

      // Lệnh /help hoặc /start
      if (/^\/(help|start)(@\S+)?$/i.test(txt)) {
        tg_('sendMessage', {chat_id: mChat, reply_to_message_id: m.message_id, text: HELP_TEXT});
        dropPendingWebhook_();
        return ContentService.createTextOutput('ok');
      }

      // Lệnh /sang, /trua, /toi
      var slotMatch = txt.match(/^\/(sang|trua|toi)(?:@\S+)?\s*(.*)$/i);
      if (slotMatch) {
        var sl = slotMatch[1].toUpperCase();
        var tp = (slotMatch[2] || '').trim();
        var inp = {slot: sl};
        if (tp) inp.seed_topic = tp;
        var okS = dispatchWorkflow_('produce_video.yml', inp);
        tg_('sendMessage', {chat_id: mChat, reply_to_message_id: m.message_id,
          text: okS
            ? ('🎬 Đã kích hoạt dựng video ca ' + sl + (tp ? ' với chủ đề:\n"' + tp + '"' : '') + '\n⏳ Chờ ~2-3 phút bot sẽ gửi video về duyệt!')
            : '⚠️ Không gọi được GitHub Actions (kiểm tra GITHUB_PAT).'});
        dropPendingWebhook_();
        return ContentService.createTextOutput('ok');
      }

      // Lệnh /tao <chủ đề>
      if (txt.indexOf('/tao') === 0) {
        var topic = txt.replace(/^\/tao(@\S+)?\s*/i, '').trim();
        var inputs = topic ? {seed_topic: topic} : {};
        var okT = dispatchWorkflow_('produce_video.yml', inputs);
        tg_('sendMessage', {chat_id: mChat, reply_to_message_id: m.message_id,
          text: okT
            ? ('🎬 Đã kích hoạt dựng video' + (topic ? ' cho chủ đề:\n"' + topic + '"' : ' từ lịch CHO_TAO') + '\n⏳ Chờ ~2-3 phút bot sẽ gửi video về duyệt!')
            : '⚠️ Không gọi được GitHub Actions (kiểm tra GITHUB_PAT).'});
        dropPendingWebhook_();
        return ContentService.createTextOutput('ok');
      }

      // Lệnh /lich
      if (txt.indexOf('/lich') === 0) {
        var data = getSheet_().getDataRange().getValues();
        var cChoTao = 0, cChoDuyet = 0, cDaDang = 0, nextTopics = [];
        for (var i = 1; i < data.length; i++) {
          var st = String(data[i][COL_STATUS - 1]);
          if (st === 'CHO_TAO') {
            cChoTao++;
            if (nextTopics.length < 3) nextTopics.push('• [' + data[i][2] + '] ' + data[i][COL_TOPIC - 1]);
          } else if (st === 'CHO_DUYET') cChoDuyet++;
          else if (st === 'DA_DANG') cDaDang++;
        }
        tg_('sendMessage', {chat_id: mChat, reply_to_message_id: m.message_id,
          text: '📊 Trạng thái lịch Google Sheets:\n'
              + '• Chờ tạo (CHO_TAO): ' + cChoTao + ' bài\n'
              + '• Chờ duyệt (CHO_DUYET): ' + cChoDuyet + ' bài\n'
              + '• Đã đăng (DA_DANG): ' + cDaDang + ' bài\n\n'
              + (nextTopics.length ? '📌 3 chủ đề sắp tới:\n' + nextTopics.join('\n') : '✨ Khi hết CHO_TAO, AI sẽ tự săn tin & sinh chủ đề mới!')
              + '\n\n🔗 Mở Sheet: https://docs.google.com/spreadsheets/d/' + DEFAULT_SHEET_ID + '/edit'});
        dropPendingWebhook_();
        return ContentService.createTextOutput('ok');
      }

      // Reply vào tin nhắn video để sửa caption
      if (m.reply_to_message) {
        var replyId = String(m.reply_to_message.message_id);
        var row = findRow_(COL_MSG_ID, replyId);
        if (row > 0) {
          getSheet_().getRange(row, COL_CAPTION).setValue(txt);
          tg_('sendMessage', {chat_id: mChat, reply_to_message_id: m.message_id,
            text: '✏️ Đã cập nhật caption mới vào Google Sheets. Bạn có thể bấm ✅ Duyệt ở tin nhắn video.'});
        }
      }
      dropPendingWebhook_();
    }
  } catch (err) {
    console.error(err);
  }
  return ContentService.createTextOutput('ok');
}

function doGet() {
  return ContentService.createTextOutput('tool-tao-video webhook alive');
}
