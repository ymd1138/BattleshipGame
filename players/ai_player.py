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
        
        # 以前の状態を保持する．
        self.previous_enemy_ships = {'w': True, 'c': True, 's': True}


    def action(self):
        # 攻撃を受けた場合，攻撃された艦がランダムな場所へ移動する．
        if self.attacked_ship:
            print(" **************** " + self.attacked_ship + " is attacked! Move! ****************")
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

        # 相手の艦のHPが0になった場合に，一度だけ初期化する．
        enemy_cond = data['condition']['enemy']
        for ship_type in ['w', 'c', 's']:
            if ship_type not in enemy_cond and self.previous_enemy_ships[ship_type]:
                if ship_type == 'w':
                    self.pred_w = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
                elif ship_type == 'c':
                    self.pred_c = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
                elif ship_type == 's':
                    self.pred_s = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
                print(" **************** Enemy " + ship_type + " destroyed! ****************")
                self.previous_enemy_ships[ship_type] = False

        # 相手の移動結果を反映する．
        if 'result' in data and 'moved' in data['result']:
            move_result = data['result']['moved']
            ship = move_result['ship']
            distance = move_result['distance']
            dx, dy = distance

            if ship == 'w':
                self.pred_w = self.move_predictions(self.pred_w, dx, dy)
            elif ship == 'c':
                self.pred_c = self.move_predictions(self.pred_c, dx, dy)
            elif ship == 's':
                self.pred_s = self.move_predictions(self.pred_s, dx, dy)

        # resultとattackedが存在すれば下に進む
        if 'result' in data and 'attacked' in data['result']:
            # 自分もしくは相手の攻撃結果を受け取る
            result = data['result']['attacked']
            position = result['position']
            hit = result.get('hit')
            near = result.get('near', [])
            
            # 自分のターンの終わりなら，自分の攻撃結果を基にスコアを更新する．
            if is_my_turn:
                # hitした場合は，hitした場所を1にして，それ以外を0にする．
                if hit == 'w':
                    self.pred_w = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
                    self.pred_w[position[0]][position[1]] = 1
                elif hit == 'c':
                    self.pred_c = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
                    self.pred_c[position[0]][position[1]] = 1
                # sに攻撃が命中した場合は撃沈するので，上で初期化する．

                # hitしなかったら，そのマスは0にする．
                else:
                    self.pred_w[position[0]][position[1]] = 0
                    self.pred_c[position[0]][position[1]] = 0
                    self.pred_s[position[0]][position[1]] = 0
                    # 正規化を行い，合計が1になるように値を修正する．
                    self.normalize(self.pred_w)
                    self.normalize(self.pred_c)
                    self.normalize(self.pred_s)
                    
                # nearの場合，周囲1マスに足して，中心は0にする．
                for n in near:
                    if n == 'w':
                        self.update_near_predictions(self.pred_w, position)
                    elif n == 'c':
                        self.update_near_predictions(self.pred_c, position)
                    elif n == 's':
                        self.update_near_predictions(self.pred_s, position)

                # nearとhitに含まれない場合，周囲のマスを0にする
                if 'w' not in near and hit != 'w':
                    self.clear_around_predictions(self.pred_w, position)
                    self.normalize(self.pred_w)
                if 'c' not in near and hit != 'c':
                    self.clear_around_predictions(self.pred_c, position)
                    self.normalize(self.pred_c)
                if 's' not in near and hit != 's':
                    self.clear_around_predictions(self.pred_s, position)
                    self.normalize(self.pred_s)
                    
            # 相手のターンの終わりなら，相手の攻撃結果を基にスコアを更新する．
            # すべての艦の予測マップについて，相手が攻撃した場所の周囲1マス（中心も含む）に足す．
            else:
                for ship_type in ['w', 'c', 's']:
                    if self.previous_enemy_ships[ship_type]:
                        self.update_around_predictions(self.pred_w if ship_type == 'w' else self.pred_c if ship_type == 'c' else self.pred_s, position)

            self.display_predictions()

    
    # 確率分布をアスキーアートで表示する
    def display_predictions(self):
        print("Prediction for 'w':")
        self.print_ascii_art(self.pred_w)
        print("Prediction for 'c':")
        self.print_ascii_art(self.pred_c)
        print("Prediction for 's':")
        self.print_ascii_art(self.pred_s)
        print()

    def print_ascii_art(self, pred):
        print("   |", end="")
        for i in range(Player.FIELD_SIZE):
            print(f"  {i}   |", end="")
        print("\n" + "--------" * Player.FIELD_SIZE)
        for i in range(Player.FIELD_SIZE):
            print(f" {i} |", end="")
            for j in range(Player.FIELD_SIZE):
                print(f" {pred[j][i]:.2f} |", end="")
            print("\n" + "--------" * Player.FIELD_SIZE)
            
    # 移動を反映させる
    def move_predictions(self, pred, dx, dy):
        new_pred = [[0] * Player.FIELD_SIZE for _ in range(Player.FIELD_SIZE)]
        for i in range(Player.FIELD_SIZE):
            for j in range(Player.FIELD_SIZE):
                ni, nj = i + dx, j + dy
                if Player.in_field([ni, nj]):
                    new_pred[ni][nj] = pred[i][j]
        return new_pred
    
    # 周囲のマスの数に基づいて，加算する値を決める．
    # nearの場合，中心の1マスは計算しない．
    def update_near_predictions(self, pred, position):
        neighbors = [(dx, dy) for dx in [-1, 0, 1] for dy in [-1, 0, 1] if (dx != 0 or dy != 0)]
        valid_neighbors = [n for n in neighbors if Player.in_field([position[0] + n[0], position[1] + n[1]])]
        factor = 1 / len(valid_neighbors)
        for dx, dy in valid_neighbors:
            x, y = position[0] + dx, position[1] + dy
            pred[x][y] += factor
        pred[position[0]][position[1]] = 0
        self.divide_two(pred)

    # 攻撃の場合，中心も含めて計算する．
    def update_around_predictions(self, pred, position):
        neighbors = [(dx, dy) for dx in [-1, 0, 1] for dy in [-1, 0, 1]]
        valid_neighbors = [n for n in neighbors if Player.in_field([position[0] + n[0], position[1] + n[1]])]
        factor = 1 / len(valid_neighbors)
        for dx, dy in valid_neighbors:
            x, y = position[0] + dx, position[1] + dy
            pred[x][y] += factor
        self.divide_two(pred)
        
    # 周囲9マスを0にする．
    def clear_around_predictions(self, pred, position):
        # 値が1のマスがあれば更新を行わない．
        if any(pred[i][j] == 1 for i in range(Player.FIELD_SIZE) for j in range(Player.FIELD_SIZE)):
            return
        neighbors = [(dx, dy) for dx in [-1, 0, 1] for dy in [-1, 0, 1]]
        valid_neighbors = [n for n in neighbors if Player.in_field([position[0] + n[0], position[1] + n[1]])]
        for dx, dy in valid_neighbors:
            x, y = position[0] + dx, position[1] + dy
            pred[x][y] = 0
                
    # 確率分布を2で割るメソッド
    def divide_two(self, pred):
        # 初回は割る必要がないため，合計が約1であり，約2ではない場合は割らないようにする．
        total = sum(sum(row) for row in pred)
        # 1に近い値の場合は割らない．つまり，1との差が0.1よりも大きいならば割る．
        if abs(total - 1) > 0.1:
            for i in range(Player.FIELD_SIZE):
                for j in range(Player.FIELD_SIZE):
                    if pred[i][j] != 0:
                        pred[i][j] /= 2

    # 正規化を行う．ヒットしなかった場合に使用する．
    def normalize(self, pred):
        total = sum(sum(row) for row in pred)
        if total > 0:
            for i in range(Player.FIELD_SIZE):
                for j in range(Player.FIELD_SIZE):
                    pred[i][j] /= total


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
