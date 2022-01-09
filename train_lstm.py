from seq2seq_lstm import Encoder,Decoder,Seq2Seq
from seq2seq_preprocessing import  target_preprocessing
import torch
import torch.nn as nn
import torch.utils.data as D
import torch.backends.cudnn as cudnn
import random
import numpy as np
import gzip,pickle
import math
import time
import argparse
from tqdm.notebook import tqdm

torch.manual_seed(0)
torch.cuda.manual_seed(0)
torch.cuda.manual_seed_all(0)
np.random.seed(0)
cudnn.benchmark = False
cudnn.deterministic = True
random.seed(0)

def init_weights(m):
    for name, param in m.named_parameters():
        nn.init.uniform_(param.data, -0.08, 0.08)

def train(model, dataloader, optimizer, criterion, clip):
    
    model.train()
    
    epoch_loss = 0
   
    for i, (input, target) in enumerate(dataloader):

        src = input
        trg = target

        if torch.cuda.is_available():
            model.cuda()
            src = src.cuda().float()
            trg = trg.cuda()
       
        # src = [16, 81, 246] batch, frame수, keypoint수
        # trg(trg)= [16, 12] = batch, trg_len

        optimizer.zero_grad()        
        
        output = model(src, trg)
        #trg = [trg len, batch size] [16,12]
        #output = [trg len, batch size, output dim]
        
        output = output[1:].view(-1, OUTPUT_DIM)
        trg = torch.transpose(trg,0,1)
        trg = trg[1:].contiguous().view(-1)
              
        #trg = [(trg len - 1) * batch size]
        #output = [(trg len - 1) * batch size, output dim]
        loss = criterion(output, trg)
        
        loss.backward()
        
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
        
        optimizer.step()
        
        epoch_loss += loss.item()
        
    return epoch_loss / len(dataloader)


def evaluate(model, dataloader, criterion):
    
    model.eval()
    
    epoch_loss = 0
    
    with torch.no_grad():
   
      for i,(input, target) in enumerate(dataloader): # valid_dataloader 정의하기
            src = input
            trg = target

            if torch.cuda.is_available():
                model.cuda()
                src = src.cuda().float()
                trg = trg.cuda()

            output = model(src, trg, 0)
            #trg = [trg len, batch size] [16,12]
            #output = [trg len, batch size, output dim]
            
            output = output[1:].view(-1, OUTPUT_DIM)
            trg = torch.transpose(trg,0,1)
            trg = trg[1:].contiguous().view(-1)
                
            #trg = [(trg len - 1) * batch size]
            #output = [(trg len - 1) * batch size, output dim]
            loss = criterion(output, trg)
            
            epoch_loss += loss.item()
            
    return epoch_loss / len(dataloader)

def epoch_time(start_time, end_time):
    elapsed_time = end_time - start_time
    elapsed_mins = int(elapsed_time / 60)
    elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
    return elapsed_mins, elapsed_secs
        
def main_train(opt):
    
    ### Data Loading
    with gzip.open('X_train.pickle','rb') as f:
        X_data = pickle.load(f)
    excel_name = opt.excel_name # 'C:/Users/winst/Downloads/menmen/train_target.xlsx'
    vocab,decoder_input = target_preprocessing(excel_name)

    ## Setting of Hyperparameter
    HID_DIM = opt.hid_dim # 512
    OUTPUT_DIM = len(vocab)+1
    N_LAYERS = 2
    DEC_DROPOUT = opt.dropout # 0.5
    emb_dim = opt.emb_dim # 128
    BATCH_SIZE = opt.batch # 32
    N_EPOCHS = opt.epochs # 50
    CLIP = 1
    model_save_path = opt.save_path # 'pt_file/'
    save_model_name = opt.pt_name # 'model1.pt'
    device = torch.device('cuda' if torch.cuda.is_available else 'cpu')
    print('device : ', device)

    ## Change data type
    X_train = torch.tensor(X_data)
    decoder_input = torch.tensor(decoder_input, dtype=torch.long)
    

    dataset = D.TensorDataset(X_train,decoder_input)
    train_dataset, val_dataset = D.random_split(dataset, [len(dataset) - int(len(dataset) * 0.2), int(len(dataset) * 0.2)]) # 8:2 split
    train_dataloader =  torch.utils.data.DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, drop_last=True)
    val_dataloader =  torch.utils.data.DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=True, drop_last=True)
    input_size = 246 # keypoint vector 길이


    ## Define Model
    enc = Encoder(input_size, HID_DIM, N_LAYERS)
    dec = Decoder(OUTPUT_DIM, emb_dim, HID_DIM, N_LAYERS, DEC_DROPOUT)
    model = Seq2Seq(enc, dec, device).to(device)
    model.apply(init_weights)

    ## Loss & Optimizer
    optimizer = torch.optim.Adam(model.parameters())
    criterion = nn.CrossEntropyLoss().to(device)


    ## Train

    best_valid_loss = float('inf')


    for epoch in tqdm(range(N_EPOCHS)):
        start_time = time.time()

        train_loss = train(model, train_dataloader, optimizer, criterion, CLIP)
        valid_loss = evaluate(model, val_dataloader, criterion)

        end_time = time.time()
        epoch_mins, epoch_secs = epoch_time(start_time, end_time)

        if valid_loss < best_valid_loss:
            best_valid_loss = valid_loss
            torch.save(model.state_dict(), f'{model_save_path}{save_model_name}')
        
        print(f'Epoch: {epoch + 1:02} | Time: {epoch_mins}m {epoch_secs}s')
        print(f'\t Train Loss: {train_loss:.3f} | Train PPL: {math.exp(train_loss):7.3f}')
        print(f'\t Val Loss: {valid_loss:.3f} | Val PPL: {math.exp(valid_loss):7.3f}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sign-Language-Train')
    parser.add_argument('--hid_dim', type=int, defualt=512,help='Number of hidden demension')
    parser.add_argument('--dropout',type=float,default=0.5,help = 'dropout ratio')
    parser.add_argument('--emb_dim',type=int,default=128,help = 'Nuber of embedding demension')
    parser.add_argument('--batch',type=int,default = 32,help='BATCH SIZE')
    parser.add_argument('--epochs',type=int, default = 50, help='EPOCH')
    parser.add_argument('--save_path',type=str,default='pt_file',help='model save path')
    parser.add_argument('--pt_name',type=str,default='model1.pt',help='save model name')
    parser.add_argument('--excel_name',type=str,default='train_target.xlsx',help='Target Excel name')
    opt = parser.parse_args()
    main_train(opt)    
