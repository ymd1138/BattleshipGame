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

        else:
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
                    player.update(get_msg)
                elif info == "waiting":
                    get_msg = sockfile.readline()
                    player.update(get_msg)
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
