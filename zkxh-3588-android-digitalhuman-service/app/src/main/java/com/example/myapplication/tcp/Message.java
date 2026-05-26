package com.example.myapplication.tcp;

import com.example.myapplication.tcp.CommonUtil;

public class Message {

    public int header;
    public int userId;
    public int msgType;
    public int msgLen;
    public int msgId;
    public byte[] content;
    public int code;

    public Message(byte header, byte userId, byte msgType, int msgLen, int msgId, byte[] content, int code) {
        super();
        this.header = CommonUtil.byteToUnsignedInt(header);
        this.userId = CommonUtil.byteToUnsignedInt(userId);
        this.msgType = CommonUtil.byteToUnsignedInt(msgType);
        this.msgLen = msgLen;
        this.msgId = msgId;
        this.content = content;
        this.code = code;
    }

    public Message() {
        super();
    }

    public int getHeader() {
        return header;
    }

    public int getUserId() {
        return userId;
    }

    public int getMsgType() {
        return msgType;
    }

    public int getMsgLen() {
        return msgLen;
    }

    public int getMsgId() {
        return msgId;
    }

    public byte[] getContent() {
        return content;
    }

    public int getCode() {
        return code;
    }

    public void setHeader(int header) {
        this.header = header;
    }

    public void setUserId(int userId) {
        this.userId = userId;
    }

    public void setMsgType(int msgType) {
        this.msgType = msgType;
    }

    public void setMsgLen(int msgLen) {
        this.msgLen = msgLen;
    }

    public void setMsgId(int msgId) {
        this.msgId = msgId;
    }

    public void setContent(byte[] content) {
        this.content = content;
    }

    public void setCode(int code) {
        this.code = code;
    }
}