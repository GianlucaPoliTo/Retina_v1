#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import warnings
#warnings.filterwarnings("ignore", "(?s).*MATPLOTLIBDATA.*", category=UserWarning)
warnings.filterwarnings("error")
from MergeCSV import merge_csv
from Pcap2Json import pcap_to_json, pcap_to_port
from split_pcap import pcap_split
import argparse
import os
import multiprocessing
import multiprocessing.pool
import time


#%%
def set_n_process (pcap_app):

    n_process = multiprocessing.cpu_count() -1
    if n_process > 30:
        n_process = 30
    if len(pcap_app) < n_process:
        n_process = len(pcap_app)
    print(f"N. worker: {n_process}")
    return n_process

def split_file(pool_tuple):
    source_pcap = pool_tuple[0]
    num_packets = pool_tuple[1]
    result_list = pool_tuple[2]
    name = os.path.basename(source_pcap).split(".")[0]
    pcap_path = os.path.dirname(source_pcap)
    new_dir = pcap_split (num_packets,source_pcap, pcap_path, name)
    new_dir_name = [os.path.join(new_dir,fs) for fs in os.listdir(new_dir)]
    result_list.append(new_dir_name)

def main2(pool_tuple):
        new_dir_name_file = pool_tuple[0]
        result_list = pool_tuple[1]
        dict_pcap_port = pcap_to_port(new_dir_name_file)
        result_list.append(dict_pcap_port)

def recursive_files(directory_p):
    pcap_app = []
    if os.path.isfile(directory_p):
        last_path = os.path.basename(os.path.normpath(directory_p))
        if last_path.split(".")[1] in "pcapng":
            return [directory_p] #torno il file su cui lavorare
        else:
            return -1 #ritorno errore
    else:
        for r, d, f in os.walk(directory_p):
            for file in f:
                if ('.pcap' in file or '.pcapng' in file):
                    pcap_app.append(os.path.join(r, file))
        return pcap_app


if __name__ == "__main__":
    with open("text.txt", "r") as f:
        print(f.read())

    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description = "RTP flow analyzer")
    parser.add_argument ("-d", "--directory", help = "Master directory", required = True)
    parser.add_argument ("-j", "--join", help = "Join all .csv" , action='store_true')
    parser.add_argument ("-js", "--json", help = "Create Json of the pcap" , action='store_true', default = False)
    parser.add_argument ("-p", "--plot", help = "Plot info" , choices=['static', 'dynamic'], default=None, type=str.lower)
    parser.add_argument ("-v", "--verbose", help = "verbosity output (txt, .json)" , action='store_true'\
	                    ,default = False)
    parser.add_argument ("-so", "--software", help = "Webex, Skype, M.Teams", choices=['webex', 'jitsi', 'teams', 'skype', 'other'], \
                        default = None, type = str.lower)
    parser.add_argument ("-s", "--screen", help = "Set True if in capture there is only video screen sharing", \
						action = 'store_true', default = None)
    parser.add_argument ("-q", "--quality", help = "HQ if HQ video 720p, LQ low 180p, MQ medium 360p",\
                        choices=['LQ', 'MQ', 'HQ'], default = None)
    parser.add_argument ("-log", "--log_dir", help = "Directory logs file", default = None)
    parser.add_argument ("-sp", "--split", help = "Set to divide pcap", type=int\
						,default = None)
    parser.add_argument ("-dp", "--drop", help = "Time drop", type=int, default = 10)
    parser.add_argument ("-gl", "--general_log", help = "general log for flows", action='store_true', default = False)
    parser.add_argument ("-ta", "--time_aggregation", help = "time window aggregation", nargs='+', type=int, default=[1])
    parser.add_argument ("-l", "--label", help = "Webex, Skype, M.Teams", default = None, type = str.lower)
    parser.add_argument ("-po", "--port", help = "Add RTP port", nargs='+', type=int, default=[])
    #aggiungere parametro per tempo aggregazione

    args = parser.parse_args()
    directory_p = args.directory
    pcap_app = recursive_files(directory_p)
    if (pcap_app == -1):
    	raise "File inserito non valido"
    n_process = set_n_process (pcap_app)
    print("Pcap to elaborate:\n")
    print(*pcap_app, sep = "\n")
    #For each .pcap in the folders, do the process
    manager = multiprocessing.Manager()
    result_list = manager.list()
    #log simile a tstat
    if args.general_log:
        OUTDIR = "logs"
        if os.path.isdir(directory_p):
            path_general_log = os.path.join(directory_p, OUTDIR)
        else:
            path_general_log = os.path.join(os.path.dirname(directory_p), OUTDIR)
        #print(f"path {os.path.isdir(path_general_log)}")
        if not os.path.isdir(path_general_log):
            os.makedirs(path_general_log)
    else:
        path_general_log = False

    #Splitto i pcap
    if args.split is not None:
    	pool= multiprocessing.Pool(processes = n_process, maxtasksperchild=1, ) #Limito il numero di processi ai core della cpu -1
    	pool_tuple = [(x, args.split, result_list) for x in pcap_app]
    	pool.imap_unordered(split_file, pool_tuple, chunksize=1)
    	pool.close()
    	pool.join()
    	pcap_app = [j for i in result_list for j in i]
    	result_list[:] = []
    #Cerco le porte
    print (f"PID main: {os.getpid()}")
    pool= multiprocessing.Pool(processes = n_process, maxtasksperchild=1, ) #Limito il numero di processi ai core della cpu -1
    pool_tuple = [(x, result_list) for x in pcap_app]
    pool.imap_unordered(main2, pool_tuple, chunksize=1)
    pool.close()
    pool.join()

    #Decodifico su porta e creo .csv
    pool= multiprocessing.Pool(processes = n_process, maxtasksperchild=1,) #Limito il numero di processi ai core della cpu -1
    pool_tuple = [(x["pcap"], x["port"]+args.port, args.screen, args.quality, args.plot, args.json, args.software, args.log_dir, \
                  args.drop, path_general_log, args.time_aggregation, args.label) for x in result_list]  #result_list, args.plot
    pool.imap_unordered(pcap_to_json, pool_tuple, chunksize=1)
    pool.close()
    pool.join()

    #%%
    if (args.join):
        for time_agg in args.time_aggregation:
    	    merge_csv(directory_p, time_agg)
