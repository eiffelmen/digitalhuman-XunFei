import { getStore, setStore } from '@/utils/store';
import { reactive } from 'vue';

export const store = reactive({
  sidebarDrawer: false,
  asrStatus: false,
  llmStatus: false,
  webrtcStatus: false,
  startRecord: false,
  defaultSettting: [
    {
      type: 'timbre',
      data: getStore({ name: 'timbre' }) || [
        {
          url: '男1.wav',
          id: 1,
          name: '男声1',
          file: 'ref_audios',
          type: 'wav'
        },
        {
          url: '女1.wav',
          id: 2,
          name: '女声1',
          file: 'ref_audios',
          type: 'wav'
        },
      ]
    },
    {
      type: 'image',
      data: getStore({ name: 'image' }) || [
        {
          url: '1.png',
          id: 1,
          name: 'AI形象1',
          file: 'templete_images',
        },
        {
          url: '2.png',
          id: 2,
          name: 'AI形象2',
          file: 'templete_images',
        },
        {
          url: '3.png',
          id: 3,
          name: 'AI形象3',
          file: 'templete_images',
        },
      ]
    },
    {
      type: 'bg',
      data: getStore({ name: 'bg' }) || [
        {
          url: '1.png',
          id: 1,
          name: '办公室',
          file: 'background',
        },
        {
          url: '2.png',
          id: 2,
          name: '雪夜',
          file: 'background',
        },
        {
          url: '3.png',
          id: 3,
          name: '竹林',
          file: 'background',
        },
      ]
    }
  ],
  digitalDefault: getStore({ name: 'digitalDefault' }) || {
    digital_human_id: 1,
    voice_type: 1,
    background_image: 2,
  },
  changeStartRecord(status) {
    this.startRecord = status
  },
  changeAsrStatus(status) {
    this.asrStatus = status
  },
  changLlmStatus(status) {
    this.llmStatus = status
  },
  changeWebrtcStatus(status) {
    this.webrtcStatus = status
  },
  changeSidebarDrawer(status) {
    this.sidebarDrawer = status
  },
  changeDigitalDefault(val) {
    this.digitalDefault = {
      ...val
    };
    setStore({
      name: 'digitalDefault',
      content: this.digitalDefault,
    });
  },
  setDefaultSetttingData(type, data) {
    const idx = this.defaultSettting.findIndex(item => item.type === type);
    this.defaultSettting[idx].data.push(data);
    setStore({
      name: type,
      content: this.defaultSettting[idx].data,
    });
  },
  deleteDefaultSetttingData(type, data) {
    const idx = this.defaultSettting.findIndex(item => item.type === type);
    this.defaultSettting[idx].data = this.defaultSettting[idx].data.filter(item => item.id !== data.id);
  },
})
