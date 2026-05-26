<script setup>
// import headShotBot from '@/assets/imgs/rabbit.jpg'
import headShotBot from '@/assets/imgs/robot.png'
import headShotUser from '@/assets/imgs/user_avatar.png'

defineProps(['message'])
</script>
<template>
  <v-avatar v-if="message.role === 'bot'" class="align-self-start avatar-box avatar-box-bot">
    <v-img :src="headShotBot"></v-img>
  </v-avatar>
  <v-card :class="{
    'bg-green-accent-4': message.role === 'user',
    'content-chat-user': message.role === 'user',
    'content-chat-bot': message.role === 'bot',
    'bg-white': message.role === 'bot'
  }" class="rounded-lg">
    <v-card-text class="text-h5 msg-text">{{ message.msg }}</v-card-text>
  </v-card>
  <v-avatar v-if="message.role === 'user'" class="align-self-end avatar-box avatar-box-user">
    <v-img :src="headShotUser"></v-img>
  </v-avatar>
</template>
<style scoped>
.bg-green-accent-4 {
  background: #74D18A !important;
  color: #fff !important;
}
.avatar-box {
  box-shadow: 0px 0px 24px 0px rgba(0,16,127,0.5);
  /* width: 80px;
  height: 80px; */

  width: 180px;
  height: 180px;
  box-shadow: 0px 0px 24px 0px rgba(0,16,127,0.5);
  border-radius: 50%;
  border: 2px solid #FFFFFF;
}
.avatar-box-user {
  margin: 0 50px 0 25px;
}
.avatar-box-bot {
  margin: 0 25px 0 50px;
}
.content-chat-user,
.content-chat-bot {
  width: fit-content;
  box-shadow: 0px 0px 24px 0px rgba(0,16,127,0.5);
  margin-top: 15px;
}
.content-chat-user {
  margin-left: 50px;
}
.content-chat-bot {
  margin-right: 50px;
}

/* 消息框颜色*/
/* .v-card{
  background: transparent !important;
} */

/* 消息文本大小 */
.msg-text {
  font-size: 80px !important;
}
</style>
