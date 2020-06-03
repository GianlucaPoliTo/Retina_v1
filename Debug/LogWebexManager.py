# -*- coding: utf-8 -*-
"""
Created on Fri Apr 24 22:18:41 2020

@author: Gianl
"""
import re
import pandas as pd
from datetime import datetime as dt
from dateutil import parser
import sys

def make_fec_dict(log, dict_flow_data):
    try:
        #Find FEC streams from Payload types
        SDP = [line for line in log if re.findall('\A[a-z]=rtpmap:', line)]
        SDP_FEC = [line for line in SDP if "x-ulpfecuc" in line]#a=rtpmap:127 x-ulpfecuc/8000
        SDP_FEC = list(set(SDP_FEC))
        PT_FEC = [int(i.replace(' ', ':').split(":")[1]) for i in SDP_FEC]

        #Find recieved FEC group IDs
        fec_ssrc_group_IDs = []
        for line in log:
            if "fec-ssrc" in line:
                fec_ssrc_group_IDs.append(re.findall('groupId=([0-9]+)', line)[0])
            
        #dictionary: ssrc of FEC : ssrc of protected stream in decimal
        ssrc_protected_streams = {}
        for group_id in fec_ssrc_group_IDs:
            right_ssrc = [re.findall(' ssrc=([0-9]+)', line1) for line1 in log if ("groupId="+group_id in line1 and " ssrc=" in line1)]
            right_ssrc = list(set([item for sublist in right_ssrc for item in sublist]))
            right_ssrc = [hex(int(element)) for element in right_ssrc]
            ssrc_protected_streams[int(group_id)] = right_ssrc

        #fec_dict has {fec key: protected stream keys}
        fec_dict = {}
        fec_keys = [key for key,value in dict_flow_data.items() if key[5] in PT_FEC] #keys of all streams with Payload type FEC

        for fec_key in fec_keys:
            fec_dict[fec_key] = []
            #if it has a csrc in dict_flow_data (which is not "fec"), it's a sent FEC
            if len(dict_flow_data[fec_key]["rtp_csrc"]) and (dict_flow_data[fec_key]["rtp_csrc"].iloc[0] != "fec"):
                fec_csrc = dict_flow_data[fec_key]["rtp_csrc"].iloc[0]
                #Go through all streams and see which ones have the same rtp_csrc but are not the same stream
                for key,value in dict_flow_data.items():
                    if len(value["rtp_csrc"]) and (value["rtp_csrc"].iloc[0] == fec_csrc) and (key != fec_key):
                        fec_dict[fec_key].append(key)

            #if it does not have a csrc in dict_flow_data, it's a received FEC
            elif not len(dict_flow_data[fec_key]["rtp_csrc"]) or (dict_flow_data[fec_key]["rtp_csrc"].iloc[0] == "fec"):
                if int(fec_key[0], 16) in ssrc_protected_streams.keys():
                    protected_streams = ssrc_protected_streams[int(fec_key[0], 16)]
                    for key,value in dict_flow_data.items():
                        if key[0] in protected_streams and not value.empty:
                            fec_dict[fec_key].append(key)

        return fec_dict
    except Exception as e:
        print('make_fec_dict: Error on line {}'.format(sys.exc_info()[-1].tb_lineno), type(e).__name__, e)
        raise NameError("make_fec_dict error")



def make_d_log(log, dict_flow_data):
    try:
        d_log = {}

        for key in dict_flow_data.keys():
            ssrc = key[0]
            inner = {k:[] for k in ["time", "ssrc_hex", "ssrc_dec", "label", "quality", "fps", "jitter"]}

            for line in log:
                #2020-04-20T14:01:59.342Z <Info> [9968] WME:0 :[SQ] [SQ] INFO: SQAudioTX - vid=0 csi=843778816 did=0 ssrc=1613872330 loss=0.000 drop=0.000 jitter=0 bytes=201518 rtp=1306 failed=0 bitrate=65016 rtt=33 bw=176000 inputRate=48552 errcnt=0 dtmf=0 codecType=4 encodeDropMs=0 rrWin=0 br=61400 type=UDP rtcp=156 cFecOn=0 fecBw=88000 fecBitRate=91392 fecPkt=1305 mari_loss=0.000 mari_qdelay=12 mari_rtt=47 mari_recvrate=130112 nbr=65016 cid__783311041
                substring = "ssrc=" + str(int(ssrc, 16)) #converto ssrc hex in dec
                if (substring in line) and ("[SQ]" in line):
                    label = re.findall(r"INFO: ([a-zA-Z]+)", line) #SQAudioTX
                    quality = re.findall(r"w*h=([0-9]+x[0-9]+)", line) #1280x720
                    fps = re.findall(r" fps=([0-9]+)", line) #15
                    jitter = re.findall(r" jitter=([0-9]+)", line) #0

                    inner["time"].append(line.split("<")[0]) # ex. 2020-04-20T14:01:59.342Z
                    inner["ssrc_hex"].append(ssrc)
                    inner["ssrc_dec"].append(int(ssrc, 16))
                    if label: inner["label"].append(label[0])
                    if quality: inner["quality"].append(quality[0])
                    if fps: inner["fps"].append(int(fps[0]))
                    if jitter: inner["jitter"].append(float(jitter[0]))

            #Metti gli informazioni dentro il dizionario d_log
            #Audio e video hanno info differenti (quality, fps) quindi cancella qualche colona su audio
            try:
                to_delete = [inner_key for inner_key in inner.keys() if not inner[inner_key]]
                for i in to_delete:
                    del inner[i]
                    #inner.pop(i, None)
                d_log[key] = pd.DataFrame(inner)
            except Exception as e:
                print(f"Cannot convert to Dataframe: {ssrc}\nError: {e}")
                pass

        for key,value in d_log.items():
            if not value.empty:
                value["timestamps"] = value["time"].apply(parser.parse).apply(dt.strftime, args =(("%Y-%m-%dT%H:%M:%S"),))
                value["timestamps"] = pd.to_datetime(value["timestamps"])

        return d_log
    except Exception as e:
        print('make_d_log: Error on line {}'.format(sys.exc_info()[-1].tb_lineno), type(e).__name__, e)
        raise NameError("make_d_log error")


def DictMerge(dict_flow_data_2, d_log, fec_dict):
    try:

        dict_merge = {}
        flows_not_in_log = []
        
        for key in dict_flow_data_2.keys():
            #Handle normal streams
            if not d_log[key].empty:
                dict_merge[key] = pd.merge( dict_flow_data_2[key], d_log[key], left_on = 'timestamps', right_on = 'timestamps', how ='inner')
            
            #Handle FEC streams
            elif key in fec_dict.keys():
                #This shouldn't happen, but just for protection
                if len(fec_dict[key]) == 0:
                    print("No flow with same groupID: ", fec_dict[key])
                    pass
                elif len(fec_dict[key]) == 1:
                    dict_merge[key] = pd.merge( dict_flow_data_2[key], d_log[fec_dict[key][0]], left_on = "timestamps", right_on = "timestamps", how = "left" ).fillna(method="ffill").fillna(method="bfill")
                    if "fps" in dict_merge[key].columns: dict_merge[key].drop(["fps", "jitter"], axis=1, inplace=True)
                    dict_merge[key]["label"] = dict_merge[key]["label"].apply(lambda x: "FEC-"+x)
                else:
                    for item in fec_dict[key]:
                        if len(d_log[item]):
                            dict_merge[key] = dict_flow_data_2[key]
                            dict_merge[key]["label"] = d_log[item]["label"].iloc[0]
                            #if video, needs also quality
                            if "Video" in d_log[item]["label"].iloc[0]:
                                dict_merge[key]["quality"] = d_log[item]["quality"].iloc[0]
                            dict_merge[key]["label"] = dict_merge[key]["label"].apply(lambda x: "FEC-"+x)
                            #As soon as I found the first good candidate for an associated stream, I fill out dict_merge[key] and break
                            break
            else:
                flows_not_in_log.append(key)
        
        #if no intersection between log data and wireshark data, delete stream (very rare cases)
        #delete empty values of dict_merge - maybe not necessary
        to_delete = [key for key,value in dict_merge.items() if not len(value["label"])]
        for i in to_delete:
            del dict_merge[i]
                    
        return dict_merge, flows_not_in_log
    
    except Exception as e:
        print('DictMerge: Error on line {}'.format(sys.exc_info()[-1].tb_lineno), type(e).__name__, e)
        raise NameError("DictMerge error")


def WebLogdf(dict_merge, pcap_name):
    try:
        dict_label = {"FEC-SQAudioRX" : 4, "FEC-SQAudioTX" : 4, \
                      "SQAudioRX" : 0,"SQAudioTX" : 0,
                      "SQVideoRX" : 1, "SQVideoTX" : 1, \
                      "FEC-SQVideoRX" : 2, "FEC-SQVideoTX" : 2, \
                      "SQScreenSender" : 1, "SQScreenReceiver" : 1
                          }

        df_train = pd.DataFrame()
        columns_drop = [ 'time', 'ssrc_hex', 'ssrc_dec','quality', 'fps', 'jitter',]
        for key in dict_merge.keys():
            dict_merge[key]["label2"] = dict_merge[key]["label"].map(dict_label)
            for ix in dict_merge[key].index:
                dict_merge[key].loc[ix, "flow"] = str(key) #aggiungo nome flusso al dataset
                dict_merge[key].loc[ix, "pcap"] = pcap_name
                if dict_merge[key].loc[ix,"label"].startswith("SQVideo"):
                    quality = min([int(i) for i in dict_merge[key].loc[ix,"quality"].split("x")]) # 180, 320 o 720
                    if quality<=180: #LQ
                        dict_merge[key].loc[ix,"label"] = 6
                    elif quality>180 and quality<=360: #MQ
                        dict_merge[key].loc[ix,"label"] = 7
                    else: #HQ
                        dict_merge[key].loc[ix,"label"] = 5
                elif dict_merge[key].loc[ix,"label"].startswith("SQScreen"):
                        dict_merge[key].loc[ix,"label"] = 3
                else:
                    dict_merge[key].loc[ix,"label"] = dict_label[dict_merge[key].loc[ix,"label"]]
            train = dict_merge[key].drop(columns_drop, axis = 1, errors = 'ignore')
            df_train = pd.concat([df_train, train])
        return df_train
    except Exception as e:
        print('LogWebex: Error on line {}'.format(sys.exc_info()[-1].tb_lineno), type(e).__name__, e)
        raise NameError("LogWebex error")
