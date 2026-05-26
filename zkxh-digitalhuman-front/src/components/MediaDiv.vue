<script setup>
import { ref, onMounted } from 'vue'
const imgSrc = ref('/ciqi.png')

const mediadiv = ref(null)

onMounted(() => {
  mediadiv.value.onmousedown = function (e) {
    //todo: 拖动不超过父容器
    // debugger
    // let shiftX = e.clientX - mediadiv.value.getBoundingClientRect().left
    // let shiftY = e.clientY - mediadiv.value.getBoundingClientRect().top
    mediadiv.value.style.position = 'absolute'
    mediadiv.value.style.zIndex = 1000
    document.body.append(mediadiv.value)

    function moveAt(pageX, pageY) {
      // todo: 待进一步完善
      // 对pagex pagey做限制
      // console.log('pagex, pagey: ', pageX, pageY)
      const maxLeft = document.getElementById('videobox').getBoundingClientRect().left
      // console.log(maxLeft)
      const maxRight = document.getElementById('videobox').getBoundingClientRect().right
      const maxTop = document.getElementById('videobox').getBoundingClientRect().top
      const maxBottom = document.getElementById('videobox').getBoundingClientRect().bottom
      if (pageX < maxLeft || pageX > maxRight || pageY < maxTop || pageY > maxBottom) {
        return
      }
      mediadiv.value.style.left = pageX - mediadiv.value.offsetWidth / 2 + 'px'
      mediadiv.value.style.top = pageY - mediadiv.value.offsetHeight / 2 + 'px'
      // mediadiv.value.style.top = pageY - shiftY + 'px'
      // mediadiv.value.style.top = pageY - shiftY + 'px'
    }
    moveAt(e.pageX, e.pageY)

    function onMouseMove(event) {
      // console.log(event.offsetX, event.offsetY)
      moveAt(event.pageX, event.pageY)
    }
    document.addEventListener('mousemove', onMouseMove)
    mediadiv.value.onmouseup = function () {
      document.removeEventListener('mousemove', onMouseMove)
      mediadiv.value.onmouseup = null
    }
    mediadiv.value.ondragstart = function () {
      return false
    }
  }
})
</script>

<template>
  <div id="mediadiv" ref="mediadiv">
    <v-img :src="imgSrc" :height="250" cover aspect-ratio="250/150" />
  </div>
</template>

<style scoped>
#mediadiv {
  height: 250px;
  width: 150px;
  background-color: black;

  cursor: move;
}
</style>
