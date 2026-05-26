<script setup>
import {
  switchDigitalHumanTemplate,
} from '@/api';
import { store } from '@/store/store';
import { getStore } from '@/utils/store';
import { computed, ref } from 'vue';
import ConfigItem from './ConfigItem.vue';

const expand = ref(false);
const curExpandType = ref(null);
const showConfirm = ref(false);
const deleteLoading = ref(false);
const emits = defineEmits(['toDiv', 'changeAvatar', 'deleteFn']);
defineExpose({
  close,
  changeCurrent,
})
const defaultImg = ref([]);
const currentImg = ref(null);
const rowType = ref({});
const isDisabled = computed(() => {
  const defaultDigital = [1, 2, 3].includes(store.digitalDefault.digital_human_id);
  const defaultBg = [1, 2, 3].includes(store.digitalDefault.background_image);
  const defaultVoice = [1, 2].includes(store.digitalDefault.voice_type);
  return defaultDigital && defaultBg && defaultVoice;
})
function toDiv() {
  close();
  emits('toDiv')
}
function toggle(val) {
  emits('changeAvatar', val, curExpandType.value);
}
function close() {
  curExpandType.value = null;
  expand.value = false;
}
function changeCurrent(key) {
  currentImg.value = defaultImg.value.find(item => item.id === store.digitalDefault[key]);
}
function showList(type, key) {
  if (curExpandType.value == type) {
    expand.value = !expand.value;
    return;
  }
  expand.value = true;
  curExpandType.value = type;
  rowType.value = {
    type: key,
  }
  const setingData = store.defaultSettting.find(item => item.type === type)?.data || [];
  const sesstionId = getStore({name: 'sessionId'}) || 0;
  defaultImg.value = [].concat(setingData.filter(item => !item.isUpload || item.isUpload && item.sessionId === sesstionId))
  console.log(defaultImg.value, '===defaultImg.value')
  changeCurrent(key);
}
function handleDefaultConfig(type, key) {
  const data = store.defaultSettting.find(item => item.type === type)?.data || [];
  return data.find(item => item.id === store.digitalDefault[key])?.name || '';
}
function resetDiv() {
  if (isDisabled.value) return;
  showConfirm.value = true;
}
async function confirmDelete() {
  if (deleteLoading.value) return;
  try {
    deleteLoading.value = true;
    const curConfig = {
      digital_human_id: 1,
      voice_type: 2,
      background_image: 3,
    }
    await switchDigitalHumanTemplate({
      ...curConfig,
      sessionid: eventBus.sessionId || 0,
    });
    store.changeDigitalDefault(curConfig);
    showConfirm.value = false;
    deleteLoading.value = false;
    emits('deleteFn');
  } catch (error) {
    deleteLoading.value = false;
  }
}
function deleteSuccess(type) {
  const data = store.defaultSettting.find(item => item.type === type)?.data || [];
  defaultImg.value = [].concat(data);
}
</script>
<template>
  <v-expand-transition>
    <div v-show="expand" class="select-config-box">
      <ConfigItem
        v-if="currentImg"
        :type="['image', 'bg', 'template'].includes(curExpandType) ? 'img': 'video'"
        :data="defaultImg"
        :rowType="rowType"
        :id="currentImg.id"
        :showUpload="false"
        @change="(val) => toggle(val)"
        @deleteSuccess="(type) => deleteSuccess(type)"
      />
    </div>
  </v-expand-transition>
  <div class="setting d-flex ma-auto text-white">
    <div @click="showList('image', 'digital_human_id')"
      class="position-relative flex-1-1 item d-flex align-center justify-center flex-column" :class="{'active': curExpandType === 'image'}">
      <div class="value">{{ handleDefaultConfig('image', 'digital_human_id') }}</div>
      <span>形象</span>
    </div>
    <div :class="{'active': curExpandType === 'timbre'}" @click="showList('timbre', 'voice_type')" class="position-relative flex-1-1 item d-flex align-center justify-center flex-column">
      <div class="value">{{ handleDefaultConfig('timbre', 'voice_type') }}</div>
      <span>音色</span>
    </div>
    <div :class="{'active': curExpandType === 'bg'}" @click="showList('bg', 'background_image')" class="position-relative flex-1-1 item d-flex align-center justify-center flex-column">
      <div class="value">{{ handleDefaultConfig('bg', 'background_image') }}</div>
      <span>背景</span>
    </div>
  </div>
  <!-- <div class="d-flex action-row ma-auto justify-center align-center">
    <div class="btn flex-1-1 d-flex justify-center align-center cursor-pointer" style="margin-right: 30px" @click="toDiv()">自定义</div>
    <div
      @click="resetDiv()"
      class="btn flex-1-1 d-flex justify-center align-center cursor-pointer"
      :class="{
        'disabled': isDisabled
      }"
    >恢复默认</div>
  </div> -->
  <v-dialog
    v-model="showConfirm"
    width="auto">
    <v-card
      title="恢复默认提示"
      text="确定要恢复默认?"
      variant="tonal"
      style="background: #fff;"
      width="300px"
      color="#000000"
    >
      <v-card-actions>
        <div class="d-flex align-center justify-end">
          <v-btn
            class="ms-auto"
            text="取消"
            @click="showConfirm = false"
          ></v-btn>
          <v-btn
            class="ms-auto"
            text="确定"
            variant="tonal"
            :loading="deleteLoading"
            @click="confirmDelete"
          ></v-btn>
        </div>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
<style scoped>
.select-config-box {
  width: 100%;
  margin-bottom: 1px;
}
.setting {
  width: 100%;
  height: 90px;
  background: rgba(0, 0, 0, 0.4);
  border-radius: 6px;
}

.item {
  font-weight: 500;
  font-size: 16px;
  padding: 20px 0;
  cursor: pointer;
  box-sizing: border-box;
  width: calc(100% / 3);
}

.item::after {
  content: "";
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  height: 60%;
  width: 1px;
  background: #fff;
}

.item.active::after,
.item:last-child::after,
.item:has(+.active)::after {
  display: none;
}

.value {
  font-weight: bold;
  font-size: 24px;
  height: 24px;
  line-height: 24px;
  margin-bottom: 10px;
  width: 95%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
}

.item span {
  display: block;
  line-height: 15px;
}

.active {
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.5);
}

.action-row {
  padding-top: 20px;
  width: 100%;
}

.action-row .btn {
  background: linear-gradient(-20deg, #4B93FF 0%, #3279E3 100%);
  box-shadow: 0px 0px 6px 0px rgba(0, 16, 127, 0.5);
  border-radius: 6px;
  font-weight: 500;
  font-size: 24px;
  color: #FFFFFF;
  height: 63px;
}
.action-row .btn.disabled {
  cursor: not-allowed;
  background: #E5E5E5;
  box-shadow: unset;
}
</style>