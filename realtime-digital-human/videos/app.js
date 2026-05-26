document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('video');

    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
            video.srcObject = stream;
        })
        .catch(error => {
            console.error('Error accessing media devices.', error);
        });

    const socket = new WebSocket('ws://your-server-host:5000/ws/process_frame');

    socket.onopen = () => {
        console.log('WebSocket connection established');
    };

    socket.onmessage = (event) => {
        const result = JSON.parse(event.data);
        if (result.error) {
            console.error('Error processing frame:', result.error);
        } else {
            console.log('Frame processed successfully:', result);
        }
    };

    socket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };

    socket.onclose = () => {
        console.log('WebSocket connection closed');
    };

    // 捕获视频帧并发送到后端
    const captureFrame = () => {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d');
        context.drawImage(video, 0, 0, canvas.width, canvas.height);

        const imageData = canvas.toDataURL('image/jpeg');
        socket.send(imageData);
    };

    const frameInterval = 1000 / 30;

    setInterval(captureFrame, frameInterval);
});
