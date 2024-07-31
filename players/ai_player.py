import json
import os
import random
import socket
import sys

sys.path.append(os.getcwd())

from lib.player_base import Player, PlayerShip


class AIPlayer(Player):

    def __init__(self, seed=0):
        random.seed(seed)

        # フィールドを5x5の配列として持っている．
        self.field = [[i, j] for i in range(Player.FIELD_SIZE)
                      for j in range(Player.FIELD_SIZE)]

        # 初期配置を非復元抽出でランダムに決める．
        ps = random.sample(self.field, 3)
        positions = {'w': ps[0], 'c': ps[1], 's': ps[2]}
        super().__init__(positions)

        # 攻撃された艦を保持する．
        self.attacked_ship = None
        
        # 相手のそれぞれの艦がいる場所の確率を保持する．
        self.pred_w = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
        self.pred_c = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
        self.pred_s = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]


    def action(self):
        # 攻撃を受けた場合，攻撃された艦がランダムな場所へ移動する．
        if self.attacked_ship:
            print(self.attacked_ship + " is attacked! Move!")
            ship = self.ships[self.attacked_ship]
            to = random.choice(self.field)
            while not ship.can_reach(to) or not self.overlap(to) is None:
                to = random.choice(self.field)
            self.attacked_ship = None
            return json.dumps(self.move(ship.type, to))

        # 攻撃
        else:
            # 3つの確率を合計して，最も値が大きいマスを攻撃する
            max = -1
            to = None
            pred = self.pred_w + self.pred_c + self.pred_s
            
            for i in range(Player.FIELD_SIZE):
                for j in range(Player.FIELD_SIZE):
                    if self.can_attack([i, j]) and pred[i][j] > max:
                        max = pred[i][j]
                        to = [i, j]

            # 初回で攻撃先が決められない場合はランダムな位置を攻撃する．
            if to is None:
                to = random.choice(self.field)
                while not self.can_attack(to):
                    to = random.choice(self.field)

            return json.dumps(self.attack(to))


    # メソッドをオーバーライド. 通知された情報で艦の状態を更新する. 
    def update(self, json_, is_my_turn):
        data = json.loads(json_)
        cond = data['condition']['me']
        for ship_type in list(self.ships):
            if ship_type not in cond:
                self.ships.pop(ship_type)
            else:
                # 攻撃された艦を取得
                if self.ships[ship_type].hp > cond[ship_type]['hp']:
                    self.attacked_ship = ship_type
                self.ships[ship_type].hp = cond[ship_type]['hp']
                self.ships[ship_type].position = cond[ship_type]['position']

        # resultとattackedが存在すれば下に進む
        if 'result' in data and 'attacked' in data['result']:
            # 自分もしくは相手の攻撃結果を受け取る
            result = data['result']['attacked']
            position = result['position']
            hit = result.get('hit')
            near = result.get('near', [])
            
            # 自分のターンの終わりなら、自分の攻撃結果を基にスコアを更新する．
            if is_my_turn:
                # hitした場合は、hitした場所を1にして、それ以外を0にする．
                if hit == 'w':
                    self.pred_w = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
                    self.pred_w[position[0]][position[1]] = 1
                elif hit == 'c':
                    self.pred_w = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
                    self.pred_w[position[0]][position[1]] = 1
                # sに攻撃が命中した場合は、撃沈するので初期化のみ．
                elif hit == 's':
                    self.pred_w = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
                # hitしなかったら、そのマスは0にする．
                else:
                    self.pred_w[position[0]][position[1]] = 0
                    self.pred_c[position[0]][position[1]] = 0
                    self.pred_s[position[0]][position[1]] = 0
                    
                # nearの場合、周囲1マスに足して、中心は0にする
                for n in near:
                    if n == 'w':
                        for dx in [-1, 0, 1]:
                            for dy in [-1, 0, 1]:
                                x, y = position[0] + dx, position[1] + dy
                                if Player.in_field([x, y]):
                                    self.pred_w[x][y] += 0.125
                        self.pred_w[position[0]][position[1]] = 0
                        self.pred_w = [[n / 2 for n in sublist] for sublist in self.pred_w]
                    elif n == 'c':
                        for dx in [-1, 0, 1]:
                            for dy in [-1, 0, 1]:
                                x, y = position[0] + dx, position[1] + dy
                                if Player.in_field([x, y]):
                                    self.pred_c[x][y] += 0.125
                        self.pred_c[position[0]][position[1]] = 0
                        self.pred_c = [[n / 2 for n in sublist] for sublist in self.pred_c]
                    elif n == 's':
                        for dx in [-1, 0, 1]:
                            for dy in [-1, 0, 1]:
                                x, y = position[0] + dx, position[1] + dy
                                if Player.in_field([x, y]):
                                    self.pred_s[x][y] += 0.125
                        self.pred_s[position[0]][position[1]] = 0
                        self.pred_s = [[n / 2 for n in sublist] for sublist in self.pred_s]

            # 相手のターンの終わりなら，相手の攻撃結果を基にスコアを更新する．
            # すべての艦の予測マップについて、相手が攻撃した場所の周囲1マス（中心も含む）に足す．
            else:
                for dx in [-1, 0, 1]:
                            for dy in [-1, 0, 1]:
                                x, y = position[0] + dx, position[1] + dy
                                if Player.in_field([x, y]):
                                    self.pred_w[x][y] += 1/9
                                    self.pred_c[x][y] += 1/9
                                    self.pred_s[x][y] += 1/9


# 仕様に従ってサーバとソケット通信を行う．
def main(host, port, seed=0):
    assert isinstance(host, str) and isinstance(port, int)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        with sock.makefile(mode='rw', buffering=1) as sockfile:
            get_msg = sockfile.readline()
            print(get_msg)
            player = AIPlayer(seed)
            sockfile.write(player.initial_condition()+'\n')

            while True:
                info = sockfile.readline().rstrip()
                print(info)
                if info == "your turn":
                    sockfile.write(player.action()+'\n')
                    get_msg = sockfile.readline()
                    player.update(get_msg, is_my_turn=True)
                elif info == "waiting":
                    get_msg = sockfile.readline()
                    player.update(get_msg, is_my_turn=False)
                elif info == "you win":
                    break
                elif info == "you lose":
                    break
                elif info == "even":
                    break
                else:
                    raise RuntimeError("unknown information")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Sample Player for Submaline Game")
    parser.add_argument(
        "host",
        metavar="H",
        type=str,
        help="Hostname of the server. E.g., localhost",
    )
    parser.add_argument(
        "port",
        metavar="P",
        type=int,
        help="Port of the server. E.g., 2000",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed of the player",
        required=False,
        default=0,
    )
    args = parser.parse_args()

    main(args.host, args.port, seed=args.seed)
