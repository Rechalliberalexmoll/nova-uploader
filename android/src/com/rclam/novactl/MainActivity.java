package com.rclam.novactl;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 直连 Nova3D 打印机 8081 接口：状态监控、暂停/停止、Z 轴控制、文件列表起印。
 * 不经过厂商云端，不需要登录，不做设备发现。
 */
public class MainActivity extends Activity {

    /** 与桌面版 NovaUploader 同代，便于两边对照。 */
    private static final String APP_VERSION = "0.6.7";
    private static final int PORT = 8081;
    private static final int POLL_MS = 3000;
    private static final int TIMEOUT_MS = 5000;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final AtomicBoolean busy = new AtomicBoolean(false);
    private volatile boolean running = true;

    private String ip = "";
    private boolean printing = false;
    private boolean paused = false;
    private String jobId = null;

    private EditText etIp;
    private TextView tvConn, tvDev, tvPill, tvJob, tvLayers, tvTime, tvParams;
    private TextView tvHistory, tvHistoryArrow, tvZHint, tvFileHint;
    private ProgressBar pb;
    private Button btnPause, btnStop, btnHome, btnPrint;
    private LinearLayout llFiles, llHistoryHead;
    private final List<Button> zButtons = new ArrayList<Button>();

    private final List<TextView> fileRowViews = new ArrayList<TextView>();
    private final List<String> fileRowNames = new ArrayList<String>();
    private String selectedFile = null;
    private String lastFileSig = "";

    // ---------------- 生命周期 ----------------

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        setContentView(R.layout.activity_main);

        etIp = (EditText) findViewById(R.id.etIp);
        tvConn = (TextView) findViewById(R.id.tvConn);
        tvDev = (TextView) findViewById(R.id.tvDev);
        tvPill = (TextView) findViewById(R.id.tvPill);
        tvJob = (TextView) findViewById(R.id.tvJob);
        tvLayers = (TextView) findViewById(R.id.tvLayers);
        tvTime = (TextView) findViewById(R.id.tvTime);
        tvParams = (TextView) findViewById(R.id.tvParams);
        tvHistory = (TextView) findViewById(R.id.tvHistory);
        tvHistoryArrow = (TextView) findViewById(R.id.tvHistoryArrow);
        tvZHint = (TextView) findViewById(R.id.tvZHint);
        tvFileHint = (TextView) findViewById(R.id.tvFileHint);
        pb = (ProgressBar) findViewById(R.id.pb);
        btnPause = (Button) findViewById(R.id.btnPause);
        btnStop = (Button) findViewById(R.id.btnStop);
        btnHome = (Button) findViewById(R.id.btnHome);
        btnPrint = (Button) findViewById(R.id.btnPrint);
        llFiles = (LinearLayout) findViewById(R.id.llFiles);
        llHistoryHead = (LinearLayout) findViewById(R.id.llHistoryHead);

        zButtons.add((Button) findViewById(R.id.zbU0));
        zButtons.add((Button) findViewById(R.id.zbU1));
        zButtons.add((Button) findViewById(R.id.zbU2));
        zButtons.add((Button) findViewById(R.id.zbU3));
        zButtons.add((Button) findViewById(R.id.zbD0));
        zButtons.add((Button) findViewById(R.id.zbD1));
        zButtons.add((Button) findViewById(R.id.zbD2));
        zButtons.add((Button) findViewById(R.id.zbD3));

        ((TextView) findViewById(R.id.tvVer)).setText("v" + APP_VERSION);

        SharedPreferences sp = getSharedPreferences("nova", MODE_PRIVATE);
        ip = sp.getString("ip", "");
        etIp.setText(ip);

        findViewById(R.id.btnSave).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String v2 = etIp.getText().toString().trim();
                if (!v2.matches("\\d{1,3}(\\.\\d{1,3}){3}")) {
                    toast("IP 格式不正确，应形如 192.168.1.61");
                    return;
                }
                ip = v2;
                getSharedPreferences("nova", MODE_PRIVATE).edit()
                        .putString("ip", ip).apply();
                lastFileSig = "";
                toast("已保存");
                ui.removeCallbacks(pollTick);
                ui.post(pollTick);
            }
        });

        findViewById(R.id.btnRefresh).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                // 立即重新拉取：清掉文件签名并重置轮询，不等下一个 3 秒周期
                lastFileSig = "";
                tvConn.setText("刷新中…");
                tvConn.setTextColor(colorOf(R.color.text_dim));
                ui.removeCallbacks(pollTick);
                ui.post(pollTick);
            }
        });

        btnPause.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (jobId == null) return;
                fire(base() + "/job/toggle/" + jobId, paused ? "继续打印" : "暂停打印");
            }
        });

        btnStop.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (jobId == null) return;
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle("停止打印")
                        .setMessage("将立即停止当前打印任务。\n\n停止后无法恢复，已打印的部分只能报废。\n\n确定吗？")
                        .setPositiveButton("确定停止", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                fire(base() + "/job/stop/" + jobId, "停止打印");
                            }
                        })
                        .setNegativeButton("取消", null)
                        .show();
            }
        });

        // Z 轴
        final double[] steps = {0.05, 1, 10, 50};
        for (int i = 0; i < 4; i++) {
            final double v = steps[i];
            zButtons.get(i).setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View x) {
                    moveZ(v);
                }
            });
            zButtons.get(i + 4).setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View x) {
                    moveZ(-v);
                }
            });
        }

        btnHome.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (printing) {
                    toast("打印中不能归位");
                    return;
                }
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle("Z 轴归位")
                        .setMessage("Z 轴将回到原点，移动幅度较大。\n请确认平台上方没有干涉、料槽已取下。\n\n确定归位？")
                        .setPositiveButton("归位", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                fire(base() + "/printer/home", "Z 轴归位");
                            }
                        })
                        .setNegativeButton("取消", null)
                        .show();
            }
        });

        // 开始打印
        btnPrint.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                final String f = selectedFile;
                if (f == null || printing) return;
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle("开始打印")
                        .setMessage("将对以下文件开始打印：\n\n" + f
                                + "\n\n打印机会立即开始工作，确定吗？")
                        .setPositiveButton("开始打印", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                fire(base() + "/file/print/" + enc(f), "开始打印 " + f);
                            }
                        })
                        .setNegativeButton("取消", null)
                        .show();
            }
        });

        // 历史折叠
        llHistoryHead.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                boolean show = tvHistory.getVisibility() != View.VISIBLE;
                tvHistory.setVisibility(show ? View.VISIBLE : View.GONE);
                tvHistoryArrow.setText(show ? "▾" : "▸");
            }
        });

        updateActionState();
        ui.post(pollTick);
    }

    @Override
    protected void onDestroy() {
        running = false;
        ui.removeCallbacks(pollTick);
        super.onDestroy();
    }

    // ---------------- 轮询 ----------------

    private final Runnable pollTick = new Runnable() {
        @Override
        public void run() {
            if (!running) return;
            if (ip.length() > 0 && busy.compareAndSet(false, true)) {
                new Thread(ioTask).start();
            }
            ui.postDelayed(this, POLL_MS);
        }
    };

    private final Runnable ioTask = new Runnable() {
        @Override
        public void run() {
            Ui tmp;
            try {
                tmp = fetchUi();
            } catch (Exception e) {
                tmp = new Ui();
                tmp.conn = "连接失败：" + shortErr(e);
                tmp.connColor = colorOf(R.color.err);
                tmp.dev = ip.isEmpty() ? "请先填写打印机 IP" : ip;
            } finally {
                busy.set(false);
            }
            final Ui u = tmp;
            ui.post(new Runnable() {
                @Override
                public void run() {
                    applyUi(u);
                }
            });
        }
    };

    private static class Ui {
        String conn = "未连接";
        int connColor = 0;
        String dev = "—";
        String pill = "未知";
        int pillColor = 0;
        String job = "—";
        String layers = "—";
        int progress = 0;
        String time = "";
        String params = "";
        String history = "—";
        boolean printing = false;
        boolean paused = false;
        String jobId = null;
        List<String> files = new ArrayList<String>();
        String fileSig = "";
    }

    private Ui fetchUi() throws Exception {
        Ui u = new Ui();
        String pinfo = safeGet(base() + "/setting/printerInfo");
        String jobsRaw = get(base() + "/job/list");

        u.conn = "已连接";
        u.connColor = colorOf(R.color.ok);
        u.dev = prettyDev(pinfo);

        JSONArray arr = new JSONArray(jobsRaw);
        JSONObject active = null;
        for (int i = 0; i < arr.length(); i++) {
            JSONObject o = arr.getJSONObject(i);
            if (o.optBoolean("printInProgress")) {
                active = o;
                break;
            }
        }

        if (active != null) {
            int total = active.optInt("totalSlices");
            int cur = active.optInt("currentSlice");
            int pct = total > 0 ? (int) Math.round(cur * 100.0 / total) : 0;
            long elapsed = active.optLong("elapsedTime");
            double avg = active.optDouble("averageSliceTime", 0) / 1000.0;
            boolean isPaused = active.optBoolean("printPaused");

            u.printing = true;
            u.paused = isPaused;
            u.jobId = active.optString("id", null);
            u.pill = isPaused ? "已暂停" : "打印中";
            u.pillColor = colorOf(isPaused ? R.color.warn : R.color.accent);
            u.job = active.optString("jobName", "—");
            u.layers = "层数　" + cur + " / " + total + "　（" + pct + "%）";
            u.progress = pct;
            long remainMs = (long) ((total - cur) * avg * 1000);
            u.time = "已用 " + dur(elapsed) + "　　剩余 "
                    + (avg > 0 ? dur(remainMs) : "计算中…");
            u.params = paramsLine(active);
        } else {
            u.printing = false;
            u.paused = false;
            u.jobId = null;
            u.pill = "空闲";
            u.pillColor = colorOf(R.color.text_dim);
            JSONObject last = lastJob(arr);
            if (last != null) {
                u.job = last.optString("jobName", "—");
                int total = last.optInt("totalSlices");
                u.layers = "共 " + total + " 层";
                u.time = "上次 " + ts(last.optLong("endPrintTime")) + "　"
                        + statusCn(last.optString("status"));
                u.params = paramsLine(last);
            }
        }
        u.history = historyText(arr);

        // 文件列表
        try {
            String fl = get(base() + "/file/list");
            JSONArray fa = new JSONArray(fl);
            StringBuilder sig = new StringBuilder();
            for (int i = 0; i < fa.length(); i++) {
                JSONObject o = fa.getJSONObject(i);
                String name = o.optString("name", "");
                String ext = o.optString("extension", "");
                if (name.length() == 0) continue;
                String full = ext.length() > 0 ? name + "." + ext : name;
                u.files.add(full);
                sig.append(full).append('|').append(o.optLong("size")).append(';');
            }
            u.fileSig = sig.toString();
        } catch (Exception ignored) {
            u.fileSig = lastFileSig;
        }
        return u;
    }

    private String paramsLine(JSONObject j) {
        double thick = j.optDouble("thickness", 0);
        long layerMs = j.optLong("layerTime", 0);
        long bottomMs = j.optLong("bottomLayersTime", 0);
        int bottomNum = j.optInt("numberOfBottomLayers", 0);
        double liftD = j.optDouble("zliftDistance", 0);
        double liftS = j.optDouble("zliftSpeed", 0);
        long curMs = j.optLong("currentSliceTime", 0);

        StringBuilder sb = new StringBuilder();
        if (thick > 0) sb.append("层高 ").append(trim(thick)).append("mm");
        if (bottomMs > 0 || layerMs > 0) {
            if (sb.length() > 0) sb.append("　·　");
            sb.append("曝光 底层 ").append(one(bottomMs / 1000.0)).append("s×").append(bottomNum)
                    .append("层 / 常规 ").append(one(layerMs / 1000.0)).append("s");
        }
        if (liftD > 0 && liftS > 0) {
            if (sb.length() > 0) sb.append("　·　");
            sb.append("抬升 ").append(trim(liftD)).append("mm @ ")
                    .append(trim(liftS)).append("mm/min");
        }
        if (curMs > 0) {
            if (sb.length() > 0) sb.append("　·　");
            sb.append("当前层 ").append(one(curMs / 1000.0)).append("s");
        }
        return sb.toString();
    }

    private String historyText(JSONArray arr) {
        List<JSONObject> list = new ArrayList<JSONObject>();
        for (int i = 0; i < arr.length(); i++) {
            try {
                list.add(arr.getJSONObject(i));
            } catch (Exception ignored) {
            }
        }
        Collections.sort(list, new Comparator<JSONObject>() {
            @Override
            public int compare(JSONObject a, JSONObject b) {
                long ta = a.optLong("endPrintTime", a.optLong("beginPrintTime", 0));
                long tb = b.optLong("endPrintTime", b.optLong("beginPrintTime", 0));
                return tb < ta ? -1 : (tb > ta ? 1 : 0);
            }
        });
        if (list.isEmpty()) return "打印机上还没有任务记录";
        StringBuilder sb = new StringBuilder();
        int n = Math.min(10, list.size());
        for (int i = 0; i < n; i++) {
            JSONObject o = list.get(i);
            long ms = o.optLong("elapsedTime", 0);
            if (i > 0) sb.append("\n");
            sb.append(ts(o.optLong("endPrintTime", o.optLong("beginPrintTime", 0))))
                    .append("  ").append(pad(statusCn(o.optString("status", "")), 4))
                    .append("  ").append(pad(ms > 0 ? dur(ms) : "—", 7))
                    .append("  ").append(o.optString("jobName", "—"));
        }
        return sb.toString();
    }

    private JSONObject lastJob(JSONArray arr) {
        JSONObject best = null;
        long bt = -1;
        for (int i = 0; i < arr.length(); i++) {
            try {
                JSONObject o = arr.getJSONObject(i);
                long t = o.optLong("endPrintTime", o.optLong("beginPrintTime", 0));
                if (t > bt) {
                    bt = t;
                    best = o;
                }
            } catch (Exception ignored) {
            }
        }
        return best;
    }

    private void applyUi(Ui u) {
        if (u.connColor != 0) tvConn.setTextColor(u.connColor);
        tvConn.setText(u.conn);
        tvDev.setText(u.dev);

        if (u.pillColor != 0) {
            tvPill.setBackgroundTintList(ColorStateList.valueOf(u.pillColor));
        }
        tvPill.setText(u.pill);
        tvJob.setText(u.job);
        tvLayers.setText(u.layers);
        pb.setProgress(u.progress);
        tvTime.setText(u.time);
        tvParams.setText(u.params);
        tvHistory.setText(u.history);

        printing = u.printing;
        paused = u.paused;
        jobId = u.jobId;

        if (!u.fileSig.equals(lastFileSig)) {
            lastFileSig = u.fileSig;
            rebuildFiles(u.files);
        }
        updateActionState();
    }

    // ---------------- 文件列表 ----------------

    private void rebuildFiles(List<String> names) {
        llFiles.removeAllViews();
        fileRowViews.clear();
        fileRowNames.clear();

        if (names.isEmpty()) {
            selectedFile = null;
            TextView t = new TextView(this);
            t.setText("打印机上没有文件");
            t.setTextColor(colorOf(R.color.text_dim));
            t.setTextSize(12);
            t.setPadding(dp(10), dp(8), dp(10), dp(8));
            llFiles.addView(t);
            return;
        }
        if (selectedFile != null && !names.contains(selectedFile)) {
            selectedFile = null;
        }
        for (int i = 0; i < names.size(); i++) {
            final String n = names.get(i);
            TextView t = new TextView(this);
            t.setText(n);
            t.setTextSize(13);
            t.setTextColor(colorOf(n.equals(selectedFile) ? android.R.color.white : R.color.text));
            t.setPadding(dp(10), dp(10), dp(10), dp(10));
            t.setBackgroundResource(n.equals(selectedFile)
                    ? R.drawable.file_row_sel : R.drawable.file_row);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT);
            lp.bottomMargin = dp(5);
            t.setLayoutParams(lp);
            t.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    selectFile(n);
                }
            });
            llFiles.addView(t);
            fileRowViews.add(t);
            fileRowNames.add(n);
        }
    }

    private void selectFile(String name) {
        selectedFile = name;
        for (int i = 0; i < fileRowViews.size(); i++) {
            boolean sel = fileRowNames.get(i).equals(name);
            fileRowViews.get(i).setBackgroundResource(
                    sel ? R.drawable.file_row_sel : R.drawable.file_row);
            fileRowViews.get(i).setTextColor(
                    colorOf(sel ? android.R.color.white : R.color.text));
        }
        updateActionState();
    }

    // ---------------- 按钮状态 ----------------

    private void updateActionState() {
        btnPause.setEnabled(printing);
        btnStop.setEnabled(printing);
        btnPause.setText(paused ? getString(R.string.resume) : getString(R.string.pause));
        btnPause.setTextColor(colorOf(paused ? R.color.ok : R.color.text));

        boolean zOk = !printing;
        for (int i = 0; i < zButtons.size(); i++) {
            zButtons.get(i).setEnabled(zOk);
        }
        btnHome.setEnabled(zOk);
        tvZHint.setText(printing ? "打印中已锁定" : "");

        btnPrint.setEnabled(!printing && selectedFile != null);
        tvFileHint.setText(printing ? "打印中，不能起印"
                : (selectedFile == null ? "未选择" : "已选"));
    }

    // ---------------- 动作 ----------------

    private void moveZ(double v) {
        if (printing) {
            toast("打印中不能移动 Z 轴");
            return;
        }
        String arrow = v > 0 ? "↑" : "↓";
        fire(base() + "/printer/move/" + fmtVal(v),
                "Z 轴 " + arrow + trim(Math.abs(v)));
    }

    private void fire(final String url, final String label) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                String msg;
                try {
                    msg = get(url);
                } catch (Exception e) {
                    msg = "失败：" + shortErr(e);
                }
                final String shown = label + " → " + summarize(msg);
                ui.post(new Runnable() {
                    @Override
                    public void run() {
                        toast(shown);
                    }
                });
                ui.post(pollTick);
            }
        }).start();
    }

    // ---------------- 网络 ----------------

    private String base() {
        return "http://" + ip + ":" + PORT;
    }

    private String get(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(TIMEOUT_MS);
        c.setReadTimeout(TIMEOUT_MS);
        c.setUseCaches(false);
        c.setRequestMethod("GET");
        try {
            int code = c.getResponseCode();
            if (code != 200) throw new Exception("HTTP " + code);
            InputStream in = c.getInputStream();
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
            in.close();
            return bo.toString("UTF-8");
        } finally {
            c.disconnect();
        }
    }

    private String safeGet(String url) {
        try {
            return get(url);
        } catch (Exception e) {
            return "";
        }
    }

    private String shortErr(Exception e) {
        String m = e.getMessage();
        if (m == null) m = e.getClass().getSimpleName();
        return m.length() > 40 ? m.substring(0, 40) : m;
    }

    // ---------------- 工具 ----------------

    /** /setting/printerInfo 返回 "型号-序列号"，如 L3130-K40-6ac87b198a。 */
    private static String prettyDev(String raw) {
        String s = raw == null ? "" : raw.trim();
        if (s.isEmpty()) return "—";
        String model = s;
        String sn = "";
        int i = s.lastIndexOf('-');
        if (i > 0 && s.length() - i - 1 >= 6) {
            model = s.substring(0, i);
            sn = s.substring(i + 1);
        }
        String friendly = friendlyModel(model);
        StringBuilder sb = new StringBuilder();
        sb.append(friendly != null ? friendly + "（" + model + "）" : model);
        if (sn.length() > 0) sb.append("\nSN ").append(sn);
        return sb.toString();
    }

    /** 型号代码到商品名的映射，认不出就原样显示代码。 */
    private static String friendlyModel(String model) {
        if (model == null) return null;
        String m = model.toUpperCase(Locale.US);
        if (m.startsWith("L3130")) return "Bene 4 Mono";
        return null;
    }

    private int colorOf(int res) {
        return getResources().getColor(res);
    }

    private int dp(int v) {
        return (int) (v * getResources().getDisplayMetrics().density + 0.5f);
    }

    private void toast(String s) {
        Toast.makeText(this, s, Toast.LENGTH_SHORT).show();
    }

    /** 接口返回压成单行摘要：成功就显示“成功”，否则截断，避免整包 JSON 刷屏。 */
    private static String summarize(String body) {
        if (body == null) return "无返回";
        String s = body.trim().replaceAll("\\s+", " ");
        if (s.length() == 0) return "无返回";
        if (s.contains("\"response\":true") || s.contains("\"response\": true")) {
            return "成功";
        }
        if (s.length() > 60) s = s.substring(0, 60) + "…";
        return s;
    }

    private static String enc(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8").replace("+", "%20");
        } catch (Exception e) {
            return s;
        }
    }

    /** 与桌面版一致：固定小数位后裁掉尾零，避免出现 1e-05 这种写法。 */
    private static String fmtVal(double v) {
        String s = String.format(Locale.US, "%.5f", v);
        if (s.indexOf('.') >= 0) {
            s = s.replaceAll("0+$", "");
            s = s.replaceAll("\\.$", "");
        }
        if (s.length() == 0 || s.equals("-")) s = "0";
        return s;
    }

    private static String statusCn(String s) {
        if (s == null) return "—";
        if (s.equals("Printing")) return "打印中";
        if (s.equals("Completed")) return "已完成";
        if (s.equals("Paused")) return "已暂停";
        if (s.equals("Cancelled")) return "已取消";
        if (s.equals("Stopped")) return "已停止";
        if (s.equals("Preparing")) return "准备中";
        return s;
    }

    private static String dur(long ms) {
        if (ms <= 0) return "—";
        long s = ms / 1000;
        long h = s / 3600;
        long m = (s % 3600) / 60;
        long sec = s % 60;
        if (h > 0) return h + "小时" + (m < 10 ? "0" : "") + m + "分";
        if (m > 0) return m + "分" + (sec < 10 ? "0" : "") + sec + "秒";
        return sec + "秒";
    }

    private static String ts(long ms) {
        if (ms <= 0) return "—";
        return new SimpleDateFormat("MM-dd HH:mm", Locale.US).format(new Date(ms));
    }

    private static String one(double v) {
        return String.format(Locale.US, "%.1f", v);
    }

    private static String trim(double v) {
        if (Math.abs(v - Math.round(v)) < 0.001) return String.valueOf(Math.round(v));
        return String.format(Locale.US, "%.2f", v);
    }

    /** 中文按两格宽对齐，让历史列表列对得齐。 */
    private static String pad(String s, int width) {
        int w = 0;
        for (int i = 0; i < s.length(); i++) {
            w += s.charAt(i) < 128 ? 1 : 2;
        }
        StringBuilder sb = new StringBuilder(s);
        while (w < width) {
            sb.append(' ');
            w++;
        }
        return sb.toString();
    }
}
