package com.faiareactnative

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.WebSettings
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private lateinit var webView: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Root layout
        val rootLayout = FrameLayout(this)

        webView = WebView(this)
        webView.webViewClient = WebViewClient()

        val webSettings: WebSettings = webView.settings
        webSettings.javaScriptEnabled = true
        webSettings.domStorageEnabled = true
        webSettings.databaseEnabled = true
        webSettings.allowFileAccess = true
        webSettings.allowContentAccess = true
        webSettings.mediaPlaybackRequiresUserGesture = false
        webSettings.javaScriptCanOpenWindowsAutomatically = true
        webSettings.setSupportMultipleWindows(true)
        webSettings.cacheMode = WebSettings.LOAD_NO_CACHE

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams
            ): Boolean {
                this@MainActivity.filePathCallback = filePathCallback
                val intent = Intent(Intent.ACTION_GET_CONTENT)
                intent.type = "*/*"
                intent.addCategory(Intent.CATEGORY_OPENABLE)
                startActivityForResult(Intent.createChooser(intent, "Select file"), 1)
                return true
            }
        }

        // Add WebView to layout
        rootLayout.addView(webView, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ))

        // Floating settings button
        val settingsBtn = Button(this)
        settingsBtn.text = "⚙"
        settingsBtn.textSize = 18f
        settingsBtn.alpha = 0.6f
        settingsBtn.setBackgroundColor(0xFF007bff.toInt())
        settingsBtn.setTextColor(0xFFFFFFFF.toInt())
        val btnParams = FrameLayout.LayoutParams(120, 120)
        btnParams.gravity = Gravity.TOP or Gravity.END
        btnParams.topMargin = 40
        btnParams.rightMargin = 20
        settingsBtn.layoutParams = btnParams
        settingsBtn.setOnClickListener { showIPDialog() }
        rootLayout.addView(settingsBtn)

        setContentView(rootLayout)

        loadServer()
    }

    private fun loadServer() {
        val prefs = getSharedPreferences("faia_config", Context.MODE_PRIVATE)
        val serverIP = prefs.getString("serverIP", "192.168.100.2") ?: "192.168.100.2"
        webView.loadUrl("http://${serverIP}:8080/")
    }

    private fun showIPDialog() {
        val prefs = getSharedPreferences("faia_config", Context.MODE_PRIVATE)
        val currentIP = prefs.getString("serverIP", "192.168.100.2") ?: "192.168.100.2"

        val input = EditText(this)
        input.setText(currentIP)
        input.hint = "e.g. 192.168.100.2"

        AlertDialog.Builder(this)
            .setTitle("Server IP Address")
            .setMessage("Enter the IP of the PC running FAIA:")
            .setView(input)
            .setPositiveButton("Connect") { _, _ ->
                val newIP = input.text.toString().trim()
                if (newIP.isNotEmpty()) {
                    prefs.edit().putString("serverIP", newIP).apply()
                    loadServer()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 1) {
            if (resultCode == Activity.RESULT_OK && data != null) {
                filePathCallback?.onReceiveValue(arrayOf(data.data!!))
            } else {
                filePathCallback?.onReceiveValue(null)
            }
            filePathCallback = null
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
