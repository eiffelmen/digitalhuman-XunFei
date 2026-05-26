package com.example.myapplication.tcp;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPInputStream;

public class CommonUtil {

    public static int byteToUnsignedInt(byte b) {
        return b & 0xFF;
    }

    public static byte[] decompress(byte[] compressedData) throws IOException {
        ByteArrayInputStream byteArrayInputStream = new ByteArrayInputStream(compressedData);
        GZIPInputStream gzipInputStream = new GZIPInputStream(byteArrayInputStream);
        ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();
 
        byte[] buffer = new byte[1024];
        int len;
        while ((len = gzipInputStream.read(buffer)) > 0) {
            byteArrayOutputStream.write(buffer, 0, len);
        }
 
        gzipInputStream.close();
        return byteArrayOutputStream.toByteArray();
    }

    public static byte[] mergeArray(byte[] array1, byte[] array2) {
        byte[] mergedArray = new byte[array1.length + array2.length];
        System.arraycopy(array1, 0, mergedArray, 0, array1.length);
        System.arraycopy(array2, 0, mergedArray, array1.length, array2.length);
        return mergedArray;
    }

    /**
     * 字节数组转十六进制字符串
     * @param data
     * @return
     */
    public static String byteToHexString(byte data) { // <-- 重新添加此方法以解决编译错误
        String hex = Integer.toHexString(data & 0xFF);
        if (hex.length() == 1) {
            hex = '0' + hex;
        }
        return hex.toUpperCase();
    }
}