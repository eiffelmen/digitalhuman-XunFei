<script setup>
import {
  deleteDigitalHuman,
  deleteUserBackground,
  deleteUserVoice,
  uploadUserBackground,
  uploadUserVoice,
} from '@/api';
import { store } from '@/store/store';
import { getAssetImgUrl } from '@/utils/getAssets';
import { getStore, setStore } from '@/utils/store';
import useMessage from '@/utils/useMessage';
import { computed, ref } from 'vue';

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  type: {
    type: String,
    default: ''
  },
  rowType: {
    type: Object,
    default: () => {}
  },
  id: {
    type: Number,
    default: 1
  },
  acceptUploadType: {
    type: String,
    default: 'image/*'
  },
  showUpload: {
    type: Boolean,
    default: true
  }
})
const fileInputRef = ref(null);
const dialog = ref(false);
const deleteObj = ref(null);
const deleteLoading = ref(false);
const emits = defineEmits(['change', 'deleteSuccess'])
const selectVal = computed(() => {
  return props.data.find(item => item.id === props.id)
})
function toggle(item) {
  if (selectVal.value.id === item.id) return;
  emits('change', item)
}
function selectFile() {
  if (!fileInputRef.value) return;
  fileInputRef.value.click();
}
async function uploadFile(e) {
  const file = e.target.files[0];
  const { type } = file;
  const fileType = props.acceptUploadType.split('/')[0];
  const uploadType = type.split('/')[1];
  if (fileType === 'image' && !['png', 'jpg', 'jpeg'].includes(uploadType)) {
    useMessage({
      type: 'error',
      message: '请上传 PNG、JPG 或 JPEG 格式的图片'
    })
    return;
  }
  if (fileType === 'audio' && !['wav', 'mp3', 'm4a', 'ogg'].includes(uploadType)) {
    useMessage({
      type: 'error',
      message: '请上传 WAV、MP3、M4A 或 OGG 格式的文件'
    })
    return;
  }
  try {
    const uploadApi = fileType === 'image' ? uploadUserBackground : uploadUserVoice;
    const formData = new FormData();
    formData.append('file', file);
    const res = await uploadApi(formData);
    const keyName = fileType === 'image' ? 'bg' : 'timbre'
    let bgImg = getStore({ name: keyName }) || [];
    const data = fileType === 'image' ? {
      url: res.image_base64,
      id: res.bg_image_id,
      name: `背景图_${res.bg_image_id}`,
      isUpload: true,
    } : {
      url: `音色_${res.voice_id}`,
      id: res.voice_id,
      name: `音色_${res.voice_id}`,
      isUpload: true,
    }
    bgImg.push(data);
    setStore({
      name: keyName,
      content: bgImg,
    });
    store.setDefaultSetttingData(keyName, data)
  } catch (error) {
    useMessage({
      type: 'error',
      message: error
    })
  }
}
function deleteItem(item) {
  deleteObj.value = item;
  dialog.value = true;
}
function deleteStorage(keyName) {
  const bgImg = (getStore({ name: keyName })||[]).filter(item => item.id !== deleteObj.value.id);
  setStore({
    name: keyName,
    content: bgImg
  })
  store.deleteDefaultSetttingData(keyName, deleteObj.value);
}
async function confirmDelete() {
  let apiFn = '';
  if (props.rowType.type === 'background_image') {
    apiFn = deleteUserBackground;
  } else if (props.rowType.type === 'voice_type') {
    apiFn = deleteUserVoice;
  } else {
    apiFn = deleteDigitalHuman;
  }
  let keyName = 'bg';
  if (props.rowType.type === 'voice_type') {
    keyName = 'timbre';
  }
  if (props.rowType.type === 'digital_human_id') {
    keyName = 'image';
  }
  if (props.rowType.type === 'background_image') {
    keyName = 'bg';
  }
  try {
    deleteLoading.value = true;
    const res = await apiFn(deleteObj.value.id);
    if (res.message) {
      useMessage({
        type: 'success',
        message: res.message
      })
    }
    deleteStorage(keyName);
    dialog.value = false;
    deleteLoading.value = false;
    emits('deleteSuccess', keyName);
  } catch (error) {
    // deleteStorage(keyName);
    // emits('deleteSuccess', keyName);
    // dialog.value = false;
    useMessage({
      type: 'error',
      message: error
    })
    deleteLoading.value = false;
  }
}
</script>
<template>
  <div class="config-item d-flex position-relative overflow-hidden">
    <v-sheet class="d-flex select-wrap">
      <div v-if="selectVal" class="select-item-value d-flex flex-column align-center justify-center">
        <div class="select-img" v-if="props.type === 'img' && selectVal.url">
          <img v-if="selectVal.isUpload" :src="selectVal.url" />
          <img v-else :src="getAssetImgUrl(`${selectVal.url}`, selectVal.file||'')" />
        </div>
        <div class="value">{{ selectVal.name || '' }}</div>
      </div>
      <v-slide-group
        show-arrows
        class="tabs-wrap"
      >
        <v-slide-group-item
          v-for="(item, index) in data"
          :key="index"
        >
          <div class="position-relative tabs-item-box d-flex flex-column align-center justify-center cursor-pointer" :class="{'tab-active': item.id === selectVal.id}" @click="toggle(item)">
            <img v-if="props.type !== 'img'" class="audio-icon" src="@/assets/speech_icon.png" />
            <div v-if="props.type === 'img'" class="tabs-item">
              <img v-if="!item.isUpload" class="img" :src="getAssetImgUrl(`${item.url}`, item.file)" />
              <img v-else class="img" :src="item.url" />
            </div>
            <span class="label">{{ item.name }}</span>
            <div @click.stop="deleteItem(item)" v-if="item.id != selectVal.id && item.isUpload" class="delete-btn position-absolute cursor-pointer">删除</div>
          </div>
        </v-slide-group-item>
      </v-slide-group>
    </v-sheet>
    <div v-if="showUpload" @click="selectFile" class="upload-btn position-absolute cursor-pointer">
      上传
      <input :accept="acceptUploadType" ref="fileInputRef" style="display: none;" type="file" @change="uploadFile" />
    </div>
    <v-dialog
      v-model="dialog"
      width="auto">
      <v-card
        title="删除提示"
        text="确定要删除该模板吗?"
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
              @click="dialog = false"
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
  </div>
</template>
<style scoped>
.config-item {
  padding: 24px 25px 20px 22px;
  background: #4D4D4D;
  border-radius: 6px;
}
.config-item,
.config-item * {
  box-sizing: border-box;
}
.select-wrap {
  width: 100%;
  background: #4D4D4D;
}
.tabs-wrap {
  flex: 1;
}
.tabs-item-box {
  width: 70px;
  margin-right: 26px;
}
.tabs-item-box:last-child {
  margin-right: 0;
}
.tabs-item-box:hover .delete-btn {
  display: block;
}
.audio-icon {
  width: 42px;
  height: 42px;
  margin-bottom:6px;
  display: none;
}
.tabs-item {
  width: 70px;
  height: 70px;
  overflow: hidden;
  margin-bottom: 7px;
  border-radius: 16px;
  box-sizing: border-box;
}
.tabs-item .img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.tabs-item-box .label {
  font-weight: 400;
  font-size: 22px;
  color: #FFFFFF;
  line-height: 21px;
  display: block;
  max-width: 70px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tab-active .tabs-item {
  border: 3px solid #0085FF;
}
.tab-active .audio-icon {
  display: block;
}
.tab-active .label {
  color: #0085FF;
}
.select-item-value {
  width: 70px;
  background: #4D4D4D;
  margin-right: 28px;
  flex-shrink: 0;
}
.select-item-value .value {
  font-weight: bold;
  font-size: 20px;
  color: #0085FF;
  line-height: 20px;
  width: 95%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
}
.select-item-value .select-img {
  width: 70px;
  height: 70px;
  overflow: hidden;
  margin-bottom: 12px;
  border-radius: 16px;
}
.select-item-value .select-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
:deep(.v-slide-group__prev),
:deep(.v-slide-group__next) {
  font-size: 46px;
  color: #fff;
  flex: 0 1 21px;
  min-width: 21px;
  height: 80px;
}
:deep(.v-slide-group__prev) {
  margin-left: 28px;
  margin-right: 25px;
}
:deep(.v-slide-group__next) {
  margin-left: 25px;
}
.config-item:has(.v-slide-group__prev) .select-item-value {
  margin-right: 0;
}
.upload-btn {
  right: 5px;
  top: 5px;
  background: linear-gradient(-20deg, #4B93FF 0%, #3279E3 100%);
  box-shadow: 0px 0px 6px 0px rgba(0,16,127,0.5);
  border-radius: 6px;
  font-weight: 400;
  font-size: 18px;
  line-height: 20px;
  padding: 2px 8px;
  color: #FFFFFF;
}
.dialog-tips {
  top: 3%;
  height: 40px;
}
.delete-btn {
  display: none;
  color: #fff;
  background: linear-gradient(-20deg, #FF4B4B 0%, #E33C3C 100%);
  border-radius: 6px;
  font-size: 14px;
  padding: 2px 4px;
  right: 0;
  top: 0;
  z-index: 9;
}
</style>