package com.faiareactnative

import android.app.Activity
import android.content.Context
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class SettingsActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val prefs = getSharedPreferences("faia_config", Context.MODE_PRIVATE)
        val currentIP = prefs.getString("serverIP", "192.168.100.12") ?: "192.168.100.12"

        val ipInput = findViewById<EditText>(R.id.ipInput)
        val saveButton = findViewById<Button>(R.id.saveButton)
        val statusText = findViewById<TextView>(R.id.statusText)

        ipInput.setText(currentIP)
        statusText.text = "Current: http://$currentIP:8080"

        saveButton.setOnClickListener {
            val newIP = ipInput.text.toString().trim()
            if (newIP.isNotEmpty()) {
                prefs.edit().putString("serverIP", newIP).apply()
                statusText.text = "Saved: http://$newIP:8080"
                setResult(Activity.RESULT_OK)
                finish()
            }
        }
    }
}
