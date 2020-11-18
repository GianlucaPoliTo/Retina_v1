#Open Tshark and run command to turn pcap to json
import subprocess
import pandas as pd
from Decode import decode_stacked
import os
import json
import sys
from json2stat import json2stat
from plotting_static import plot_stuff_static
from plotting import plot_stuff
from Martino_log import compute_stats
import copy
import sys
import numpy as np

def pcap_to_port(source_pcap):
    try:
    # Retrive all STUN packets
        #command = ['tshark', '-r', source_pcap, '-l', '-n', '-T', 'ek', '-Y (stun)']
        command = f"tshark -r {source_pcap} -T fields  -E separator=? -E header=n -e udp.srcport -e udp.dstport"
        output, e = subprocess.Popen(command, stdout=subprocess.PIPE, encoding = 'utf-8', errors="ignore", shell=True).communicate()
    except Exception as e:
        print ("Errore in pcap_to_json: {}".format(e))
        process.kill()
        raise e
    # I've got all STUN packets: need to find which ports are used by RTP
    used_port=set([int(x) for x in output.replace('\n','?').split('?') if x != ''])
    #used_port = set([10000, 50412])
    #for obj in decode_stacked(output):
    #    try:
    #        if 'index' in obj.keys():
    #            continue
    #        if 'stun' in obj['layers'].keys() and "0x00000101" in obj['layers']["stun"]["stun_stun_type"]:          #0x0101 means success
    #            used_port.add(obj['layers']["udp"]["udp_udp_srcport"])
    #            used_port.add(obj['layers']["udp"]["udp_udp_dstport"])
    #    except:
    #        continue
    return {"pcap" : source_pcap, "port" : list(used_port)}

def pcap_to_json(tuple_param): #source_pcap, used_port
  #  print (f"PID 2json: {os.getpid()}")
    try:
        source_pcap = tuple_param[0] # path del pcap
        used_port = tuple_param[1] #porte stun recuperate dal pcap
        screen = tuple_param[2] # old per webex, tutti i flussi video sono etichettati come SS
        quality = tuple_param[3] #old per webex, specifica qualità flussi video, (devono essere tutti uguali)
        plot = tuple_param[4] # se True crea Plot
        loss_rate = tuple_param[5] #
        software = tuple_param[6] # webex jitsi ..
        file_log = tuple_param[7] #directory padre dei file .log
        time_drop = tuple_param[8] # durata in secondi minima che deve avere un flusso
        general_log = tuple_param[9] #se c'è contiene il path dove salvare il file, altrimenti False
        time_aggregation = tuple_param[10]
        label = tuple_param[11]
        name = os.path.basename(source_pcap).split(".")[0] # nome del pcap senza estensione
        pcap_path = os.path.dirname(source_pcap) # percorso pcap senza file
        filtro = "rtp.version==2"
        port_add = []
        for port in used_port:
            port_add.append("-d udp.port==" + str(port) + ",rtp")

        command = f"""tshark -r {source_pcap} -Y {filtro} \
                     -T fields {" ".join(port_add)} -E separator=? -E header=y -e frame.time_epoch -e frame.number \
                     -e frame.len -e udp.srcport \
                     -e udp.dstport  -e udp.length  -e rtp.p_type -e rtp.ssrc -e rtp.timestamp \
                     -e rtp.seq  -e rtp.marker -e rtp.csrc.item -e ip.src -e ipv6.src -e ip.dst -e ipv6.dst  --enable-heuristic rtp_stun"""
        o,e= subprocess.Popen(command, encoding = 'utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE ,shell=True).communicate()
        r = o.split("\n")
        name_col = r.pop(0)
        name_col = [e for e in name_col.split("?") if e not in ('ipv6.dst','ipv6.src')]
        #rint(f"string len: {len(r)}")
        del(o)
        rr = [x.split("?")[0:12]+ list(filter(None,x.split("?")[12:16])) for x in r if '' not in x.split("?")[0:9]] #devo tenere solo ipv4 o 6 per ogni pacchetto
        del(r)
        df = pd.DataFrame(rr, columns=name_col)
        df['rtp.p_type']=df['rtp.p_type'].apply(lambda x: x.split(",")[0]) # a volte jitsi mteams hanno più p_type, prendiamo solo il primo
        df = df.astype({'frame.time_epoch': 'float64', 'frame.number' : "int32", 'frame.len' : "int32", \
                        'udp.length' : "int32", 'rtp.p_type' : "int", \
                        'rtp.timestamp' : np.int64, "udp.srcport" : "int32", \
                         "udp.dstport" : "int32", 'rtp.marker' : "int32", 'rtp.seq' : "int32", \
                   })
        df = df.rename(columns ={
            'frame.time_epoch' : 'timestamps',
            'frame.number' : 'frame_num',
            'frame.len' : "len_frame",
            'ip.src' : 'ip_src',
            'ip.dst' : 'ip_dst',
            'udp.srcport' : 'prt_src',
            'udp.dstport' : 'prt_dst',
            'udp.length' :  'len_udp',
            'rtp.p_type' : 'p_type',
            'rtp.ssrc' : 'ssrc',
            'rtp.timestamp' : 'rtp_timestamp',
            'rtp.seq' : 'rtp_seq_num',
            'rtp.marker' : 'rtp_marker',
             'rtp.csrc.item' : 'rtp_csrc'
                })
        df["rtp_csrc"].replace('',"fec", inplace=True)
        if software=="webex":
            columns=["ssrc", "ip_src", "ip_dst", "prt_src", "prt_dst" , "p_type"]
        elif label=="skype":
            columns=["ssrc", "ip_src", "ip_dst", "prt_src", "prt_dst"]
        elif label=="mteams":
            columns=["ssrc", "ip_src", "ip_dst", "prt_src", "prt_dst"]
        else:
            columns=["ssrc", "ip_src", "ip_dst", "prt_src", "prt_dst" , "p_type"]
        gb= df.groupby(columns)
        dict_flow_data = {x : gb.get_group(x) for x in gb.groups if x is not None and np.max(gb.get_group(x)["timestamps"]) - np.min(gb.get_group(x)["timestamps"])>time_drop}
        df_unique_flow = pd.DataFrame(columns = columns)
        for key in dict_flow_data.keys():
            df_unique_flow=df_unique_flow.append(pd.Series(key, index=columns), ignore_index=True)
        if general_log: #genera log simile a tstat
            general_dict_info = {}
            for flow_id in dict_flow_data:
                s = compute_stats(copy.deepcopy(dict_flow_data[flow_id]),flow_id, name+".pcapng")
                if s is not None:
                    general_dict_info[flow_id] = s
                    general_df=pd.DataFrame.from_dict(general_dict_info, orient='index').reset_index(drop = True)
                    general_df.to_csv(os.path.join(general_log,name+"_gl.csv"))
        # dict list etc sono passate by reference, attenzione!!
        for time_agg in time_aggregation:
            dataset_dropped = json2stat(copy.deepcopy(dict_flow_data), pcap_path, name, time_agg, screen = screen, quality = quality, software = software, file_log = file_log, label=label, loss_rate=loss_rate)
        if plot == "static":
            plot_path = os.path.join(pcap_path,name)
            plot_stuff_static(plot_path, dict_flow_data, df_unique_flow)
        elif plot == "dynamic":
            plot_path = os.path.join(pcap_path,name)
            plot_stuff(plot_path, dict_flow_data, df_unique_flow, dataset_dropped, software)
        else:
            pass

    except Exception as e:
        print('Pcap2Json: Error on line {}'.format(sys.exc_info()[-1].tb_lineno), type(e).__name__, e)
        raise NameError("Pcap2Json error")
    return
