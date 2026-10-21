package com.pcontrol.app;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;
import android.window.OnBackInvokedDispatcher;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Casca do PControl: acha o PC (Wi-Fi de casa ou Tailscale) e abre a interface dele em tela cheia.
 */
public class MainActivity extends Activity {

    private static final String SETUP_URL = "file:///android_asset/setup.html";
    private static final int DEFAULT_PORT = 8765;
    private static final int DISCOVERY_PORT = 8766;
    private static final int FILE_CHOOSER = 1;
    private static final int BG = 0xFF0D0F13;

    private final ExecutorService io = Executors.newCachedThreadPool();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final AtomicBoolean connecting = new AtomicBoolean(false);

    private WebView web;
    private SharedPreferences prefs;
    private String baseUrl;
    private String pendingShare;
    private ValueCallback<Uri[]> fileCallback;
    private boolean immersive;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("pcontrol", MODE_PRIVATE);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(BG);
        web = new WebView(this);
        web.setBackgroundColor(BG);
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        setupEdgeToEdge(root);
        setupWebView();
        setupBack();

        handleShare(getIntent());
        web.loadUrl(SETUP_URL);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleShare(intent);
        if (baseUrl != null && pendingShare != null) deliverShare();
    }

    @Override
    protected void onDestroy() {
        io.shutdownNow();
        web.destroy();
        super.onDestroy();
    }

    // --- janela -----------------------------------------------------------

    @SuppressWarnings("deprecation")
    private void setupEdgeToEdge(View root) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            getWindow().setDecorFitsSystemWindows(false);
        } else {
            root.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
        getWindow().setStatusBarColor(Color.TRANSPARENT);
        getWindow().setNavigationBarColor(BG);
        // A página não enxerga as barras do sistema nem o teclado: o espaço é reservado aqui.
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int left, top, right, bottom;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                Insets ime = insets.getInsets(WindowInsets.Type.ime());
                left = bars.left;
                top = bars.top;
                right = bars.right;
                bottom = Math.max(bars.bottom, ime.bottom);
            } else {
                left = insets.getSystemWindowInsetLeft();
                top = insets.getSystemWindowInsetTop();
                right = insets.getSystemWindowInsetRight();
                bottom = insets.getSystemWindowInsetBottom();
            }
            v.setPadding(left, top, right, bottom);
            return insets;
        });
    }

    @SuppressWarnings("deprecation")
    private void setFullscreen(boolean on) {
        immersive = on;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c == null) return;
            if (on) {
                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                c.hide(WindowInsets.Type.systemBars());
            } else {
                c.show(WindowInsets.Type.systemBars());
            }
        } else {
            int flags = View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION;
            if (on) {
                flags |= View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION;
            }
            getWindow().getDecorView().setSystemUiVisibility(flags);
        }
    }

    private void setupBack() {
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::handleBack);
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        handleBack();
    }

    /** Fecha o que estiver aberto na página (menus, tela cheia); se não tiver nada, vai pro fundo. */
    private void handleBack() {
        if (baseUrl == null) {
            moveTaskToBack(true);
            return;
        }
        web.evaluateJavascript("window.pcontrolBack ? window.pcontrolBack() : false", result -> {
            if (!"true".equals(result)) moveTaskToBack(true);
        });
    }

    // --- WebView ----------------------------------------------------------

    private void setupWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setTextZoom(100);
        s.setUserAgentString(s.getUserAgentString() + " PControlApp/1.0");
        CookieManager.getInstance().setAcceptCookie(true);
        web.addJavascriptInterface(new Bridge(), "PControlApp");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                if ("file".equals(url.getScheme())) return false;
                if (baseUrl != null && sameOrigin(url, Uri.parse(baseUrl))) return false;
                // Links de fora abrem no navegador do celular.
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, url));
                } catch (ActivityNotFoundException ignored) {
                }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (baseUrl != null && url.startsWith(baseUrl) && pendingShare != null) deliverShare();
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame() && baseUrl != null) showSetup("lost");
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = params.createIntent();
                intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try {
                    startActivityForResult(intent, FILE_CHOOSER);
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_CHOOSER || fileCallback == null) return;
        Uri[] result = null;
        if (resultCode == RESULT_OK && data != null) {
            ClipData clip = data.getClipData();
            if (clip != null) {
                result = new Uri[clip.getItemCount()];
                for (int i = 0; i < clip.getItemCount(); i++) result[i] = clip.getItemAt(i).getUri();
            } else if (data.getData() != null) {
                result = new Uri[]{data.getData()};
            }
        }
        fileCallback.onReceiveValue(result);
        fileCallback = null;
    }

    private static boolean sameOrigin(Uri a, Uri b) {
        return a.getHost() != null && a.getHost().equalsIgnoreCase(b.getHost()) && a.getPort() == b.getPort();
    }

    private void showSetup(String mode) {
        baseUrl = null;
        if (immersive) setFullscreen(false);
        web.loadUrl(SETUP_URL + "#" + mode);
    }

    private void loadPc(String base) {
        baseUrl = base;
        String token = prefs.getString("token", null);
        if (token != null) setSessionCookie(base, token);
        web.loadUrl(base + "/");
    }

    private void setSessionCookie(String base, String token) {
        CookieManager cm = CookieManager.getInstance();
        cm.setCookie(base, "pc_session=" + token + "; Path=/; Max-Age=7776000; SameSite=Lax");
        cm.flush();
    }

    private void callSetup(String js) {
        main.post(() -> {
            if (baseUrl == null) web.evaluateJavascript(js, null);
        });
    }

    // --- compartilhar ------------------------------------------------------

    private void handleShare(Intent intent) {
        if (intent != null && Intent.ACTION_SEND.equals(intent.getAction())) {
            String text = intent.getStringExtra(Intent.EXTRA_TEXT);
            if (text != null && !text.trim().isEmpty()) pendingShare = text;
            intent.setAction(Intent.ACTION_MAIN);
        }
    }

    private void deliverShare() {
        String text = pendingShare;
        pendingShare = null;
        web.evaluateJavascript("window.pcontrolShare && window.pcontrolShare(" + JSONObject.quote(text) + ")", null);
    }

    // --- achar o PC --------------------------------------------------------

    private static String normalizeAddress(String text) {
        String s = text.trim();
        if (s.isEmpty()) return null;
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "http://" + s;
        Uri u = Uri.parse(s);
        if (u.getHost() == null || u.getHost().isEmpty()) return null;
        int port = u.getPort() > 0 ? u.getPort() : DEFAULT_PORT;
        return u.getScheme() + "://" + u.getHost() + ":" + port;
    }

    private static boolean isTailscale(String base) {
        String host = Uri.parse(base).getHost();
        if (host == null) return false;
        if (host.endsWith(".ts.net")) return true;
        String[] p = host.split("\\.");
        if (p.length != 4) return false;
        try {
            int a = Integer.parseInt(p[0]), b = Integer.parseInt(p[1]);
            return a == 100 && b >= 64 && b <= 127;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    private static boolean ping(String base, int timeoutMs) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(base + "/api/ping").openConnection();
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            if (c.getResponseCode() != 200) return false;
            try (InputStream in = c.getInputStream()) {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[1024];
                int n;
                while ((n = in.read(buf)) > 0 && out.size() < 4096) out.write(buf, 0, n);
                return out.toString("UTF-8").contains("pcontrol");
            }
        } catch (IOException e) {
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private static List<InetAddress> broadcastTargets() {
        List<InetAddress> targets = new ArrayList<>();
        try {
            targets.add(InetAddress.getByName("255.255.255.255"));
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    if (ia.getBroadcast() != null && !targets.contains(ia.getBroadcast())) targets.add(ia.getBroadcast());
                }
            }
        } catch (IOException ignored) {
        }
        return targets;
    }

    /** Pergunta na rede "tem algum PControl aí?" e junta as respostas por 2 segundos. */
    private static JSONArray discover() {
        JSONArray found = new JSONArray();
        Set<String> seen = new HashSet<>();
        byte[] question = "PCONTROL_DISCOVER".getBytes(StandardCharsets.US_ASCII);
        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setBroadcast(true);
            socket.setSoTimeout(350);
            List<InetAddress> targets = broadcastTargets();
            long end = System.currentTimeMillis() + 2200;
            int round = 0;
            while (System.currentTimeMillis() < end) {
                if (round++ % 2 == 0 && round < 6) {
                    for (InetAddress t : targets) {
                        try {
                            socket.send(new DatagramPacket(question, question.length, t, DISCOVERY_PORT));
                        } catch (IOException ignored) {
                        }
                    }
                }
                byte[] buf = new byte[1024];
                DatagramPacket packet = new DatagramPacket(buf, buf.length);
                try {
                    socket.receive(packet);
                } catch (SocketTimeoutException e) {
                    continue;
                }
                try {
                    JSONObject answer = new JSONObject(new String(packet.getData(), 0, packet.getLength(), StandardCharsets.UTF_8));
                    if (!"pcontrol".equals(answer.optString("app"))) continue;
                    String url = "http://" + packet.getAddress().getHostAddress() + ":" + answer.optInt("port", DEFAULT_PORT);
                    if (seen.add(url)) found.put(new JSONObject().put("name", answer.optString("name", "PC")).put("url", url));
                } catch (Exception ignored) {
                }
            }
        } catch (IOException ignored) {
        }
        return found;
    }

    /** Tenta o Wi-Fi primeiro, depois o Tailscale; se o IP de casa mudou, procura na rede. */
    private void autoConnect() {
        if (!connecting.compareAndSet(false, true)) return;
        io.execute(() -> {
            try {
                String lan = prefs.getString("lan", null);
                String ts = prefs.getString("tailscale", null);
                if (lan == null && ts == null) {
                    callSetup("onNeedSetup()");
                    return;
                }
                if (lan != null) {
                    callSetup("onStatus('Procurando o PC no Wi-Fi…')");
                    if (ping(lan, 1500)) {
                        main.post(() -> loadPc(lan));
                        return;
                    }
                }
                if (ts != null) {
                    callSetup("onStatus('Conectando pelo Tailscale…')");
                    if (ping(ts, 5000)) {
                        main.post(() -> loadPc(ts));
                        return;
                    }
                }
                callSetup("onStatus('Procurando na rede…')");
                JSONArray found = discover();
                if (found.length() > 0) {
                    String host = prefs.getString("host", "");
                    JSONObject pick = found.getJSONObject(0);
                    for (int i = 0; i < found.length(); i++) {
                        if (found.getJSONObject(i).optString("name").equalsIgnoreCase(host)) pick = found.getJSONObject(i);
                    }
                    String url = pick.getString("url");
                    prefs.edit().putString("lan", url).apply();
                    main.post(() -> loadPc(url));
                    return;
                }
                callSetup("onConnectFailed()");
            } catch (Exception e) {
                callSetup("onConnectFailed()");
            } finally {
                connecting.set(false);
            }
        });
    }

    /** A página perdeu a conexão: talvez o celular saiu do Wi-Fi. Tenta o outro caminho. */
    private void reconnect() {
        if (!connecting.compareAndSet(false, true)) return;
        io.execute(() -> {
            try {
                String current = baseUrl;
                String lan = prefs.getString("lan", null);
                String ts = prefs.getString("tailscale", null);
                for (String candidate : new String[]{lan, ts}) {
                    if (candidate == null || candidate.equals(current)) continue;
                    if (ping(candidate, candidate.equals(lan) ? 1500 : 5000)) {
                        main.post(() -> loadPc(candidate));
                        return;
                    }
                }
            } finally {
                connecting.set(false);
            }
        });
    }

    // --- ponte com a página ------------------------------------------------

    private class Bridge {
        @JavascriptInterface
        public String getState() {
            try {
                return new JSONObject()
                        .put("lan", prefs.getString("lan", null))
                        .put("tailscale", prefs.getString("tailscale", null))
                        .put("host", prefs.getString("host", null))
                        .toString();
            } catch (Exception e) {
                return "{}";
            }
        }

        @JavascriptInterface
        public void autoConnect() {
            MainActivity.this.autoConnect();
        }

        @JavascriptInterface
        public void discover() {
            io.execute(() -> {
                JSONArray found = MainActivity.discover();
                callSetup("onDiscovered(" + found + ")");
            });
        }

        @JavascriptInterface
        public void useAddress(String address) {
            String base = normalizeAddress(address);
            if (base == null) {
                callSetup("onConnectFailed('Endereço inválido.')");
                return;
            }
            io.execute(() -> {
                callSetup("onStatus('Testando " + base + "…')");
                if (!ping(base, isTailscale(base) ? 6000 : 3000)) {
                    callSetup("onConnectFailed('O PC não respondeu nesse endereço.')");
                    return;
                }
                prefs.edit().putString(isTailscale(base) ? "tailscale" : "lan", base).apply();
                main.post(() -> loadPc(base));
            });
        }

        @JavascriptInterface
        public void forget() {
            prefs.edit().clear().apply();
            CookieManager.getInstance().removeAllCookies(null);
        }

        @JavascriptInterface
        public void back() {
            main.post(() -> {
                if (baseUrl == null) autoConnect();
            });
        }

        @JavascriptInterface
        public void connected(String json) {
            try {
                JSONObject o = new JSONObject(json);
                SharedPreferences.Editor e = prefs.edit();
                if (!o.isNull("lan")) e.putString("lan", o.getString("lan"));
                if (!o.isNull("tailscale")) e.putString("tailscale", o.getString("tailscale"));
                if (!o.isNull("host")) e.putString("host", o.getString("host"));
                e.apply();
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void saveToken(String token) {
            prefs.edit().putString("token", token).apply();
            // O mesmo login vale para o endereço do Wi-Fi e o do Tailscale.
            main.post(() -> {
                for (String key : new String[]{"lan", "tailscale"}) {
                    String base = prefs.getString(key, null);
                    if (base != null) setSessionCookie(base, token);
                }
            });
        }

        @JavascriptInterface
        public void clearToken() {
            prefs.edit().remove("token").apply();
            CookieManager.getInstance().removeAllCookies(null);
        }

        @JavascriptInterface
        public void openSettings() {
            main.post(() -> showSetup("settings"));
        }

        @JavascriptInterface
        public void reconnect() {
            MainActivity.this.reconnect();
        }

        @JavascriptInterface
        public void setImmersive(boolean on) {
            main.post(() -> setFullscreen(on));
        }

        @JavascriptInterface
        public void download(String url, String name) {
            main.post(() -> {
                try {
                    String safe = name.replaceAll("[\\\\/:*?\"<>|]", "_");
                    DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
                    String cookie = CookieManager.getInstance().getCookie(url);
                    if (cookie != null) r.addRequestHeader("Cookie", cookie);
                    r.setTitle(safe);
                    r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, safe);
                    ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(r);
                } catch (Exception e) {
                    Toast.makeText(MainActivity.this, "Não deu para baixar: " + e.getMessage(), Toast.LENGTH_LONG).show();
                }
            });
        }
    }
}
