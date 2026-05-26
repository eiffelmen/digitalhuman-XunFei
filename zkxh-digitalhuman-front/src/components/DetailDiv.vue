<script setup>
import { store } from "@/store/store";
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {v4 as uuidv4} from 'uuid';

const router = useRouter();
const gotoSettingsPage = () => {
  router.push("/settings/human");
};

const deviceid = ref("");

async function updateWebId() {
  if (!deviceid.value) {
    console.warn("请输入设备ID");
    return;
  }
  try {
    let uuid ="";
    if(!localStorage.getItem("webid")) {
      uuid = uuidv4();
      localStorage.setItem("webid", uuid);
    }else{
      console.log("Web ID already exists:", localStorage.getItem("webid"));
      uuid = localStorage.getItem("webid");
    }

    console.log("Updating device ID to:", deviceid.value);
    console.log("Current web ID:", uuid);


    const response = await fetch("/api/web_register_device", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deviceid: deviceid.value,
        webid: uuid,
      }),
    });
    if (!response.ok) {
      console.error("网络错误，无法更新device id");
      return;
    }
    const data = await response.json();
    if (data.status === "success") {
      localStorage.setItem("deviceid", data.deviceid);
      // localStorage.setItem("webid", data.webid);
      console.log("device id updated successfully:", data.deviceid);
    } else {
      console.error("更新 device id 失败:", data.message);
    }
  } catch (err) {
    console.error("请求异常:", err);
  }
}
onMounted(() => {
  if (localStorage.getItem("deviceid")) {
    deviceid.value = localStorage.getItem("deviceid");
  }
});
</script>
<template>
  <div>
    <!-- <v-row> -->
    <!-- <v-col cols="12"> -->
    <div>asr状态: {{ store.asrStatus ? "正常" : "未连接" }}</div>
    <div>llm状态: {{ store.llmStatus ? "正常" : "未连接" }}</div>
    <div>webrtc状态: {{ store.webrtcStatus ? "正常" : "未连接" }}</div>
    <input v-model="deviceid" style="color: white;"></input>
    <input
      v-model="deviceid"
      placeholder="填写deviceid"
      style="color: white; width: 300px; font-size: 40px"
    />
    <v-btn @click="updateWebId" style="font-size: 40px; height: auto"
      >更新id</v-btn
    >
    <!-- <div> -->
    <!-- <v-btn style="font-size: 40px;height: auto;" @click="gotoSettingsPage">设置</v-btn> -->
    <!-- </div> -->
    <!-- </v-col> -->
    <!-- </v-row> -->
  </div>
</template>
